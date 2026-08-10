from __future__ import annotations

import ftplib
import io
import logging
import os
import socket
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

import requests

from .models import Company


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class FloridaDailyFile:
    file_date: date
    records: list[Company]
    transport: str


def parse_corporate_line(line: str) -> Company | None:
    """Parse Florida's official 1,440-character corporate fixed-width record."""
    if len(line) < 480:
        return None
    document_number = line[0:12].strip()
    name = line[12:204].strip()
    status = line[204:205].strip()
    filing_type = line[205:220].strip()
    city = line[304:332].strip()
    state = line[332:334].strip()
    postal_code = line[334:344].strip()
    country = line[344:346].strip()
    raw_file_date = line[472:480].strip()
    if not document_number or not name or len(raw_file_date) != 8:
        return None
    try:
        incorporated_on = datetime.strptime(raw_file_date, "%m%d%Y").date().isoformat()
    except ValueError:
        return None
    safe_number = "USFL" + "".join(
        character for character in document_number.upper() if character.isalnum()
    )
    return Company(
        company_number=safe_number,
        name=name,
        incorporated_on=incorporated_on,
        company_type=filing_type,
        status=status,
        address={
            "locality": city,
            "region": state,
            "postal_code": postal_code,
            "country": country,
            "source_document_number": document_number,
        },
    )


def parse_corporate_file(content: bytes) -> list[Company]:
    text = content.decode("cp1252", errors="replace")
    return [company for line in text.splitlines() if (company := parse_corporate_line(line))]


class FloridaSunbizClient:
    """Download the latest official Florida daily corporate file.

    Sunbiz describes the portal as usable by a secure FTP client. We try SFTP,
    FTPS and HTTPS so the scheduled job survives portal transport differences.
    """

    def __init__(self, config: dict, session: requests.Session | None = None) -> None:
        self.config = config
        self.host = str(config.get("host", "sftp.floridados.gov"))
        default_username = str(config.get("username", "Public"))
        default_password = str(config.get("password", "PubAccess1845!"))
        self.username = os.getenv("FLORIDA_SUNBIZ_USERNAME", "").strip() or default_username
        self.password = os.getenv("FLORIDA_SUNBIZ_PASSWORD", "").strip() or default_password
        self.session = session or requests.Session()

    def latest(self, *, today: date | None = None) -> FloridaDailyFile:
        today = today or date.today()
        dates = list(self._candidate_dates(today))
        errors: list[str] = []
        for transport in self.config.get("transport_order", ["sftp", "ftps", "https"]):
            try:
                file_date, content = getattr(self, f"_download_{transport}")(dates)
                records = parse_corporate_file(content)
                if not records:
                    raise RuntimeError("download contained no valid corporate records")
                LOGGER.info(
                    "Downloaded %s Sunbiz records for %s via %s",
                    len(records), file_date, transport,
                )
                return FloridaDailyFile(file_date, records, transport)
            except Exception as exc:
                errors.append(f"{transport}: {exc}")
                LOGGER.warning("Sunbiz %s download failed: %s", transport, exc)
        raise RuntimeError("Could not download a recent Sunbiz file; " + "; ".join(errors))

    def _candidate_dates(self, today: date) -> Iterable[date]:
        lookback = int(self.config.get("lookback_days", 10))
        for offset in range(lookback + 1):
            candidate = today - timedelta(days=offset)
            if candidate.weekday() < 5:
                yield candidate

    @staticmethod
    def _path(candidate: date) -> str:
        return f"doc/cor/{candidate:%Y%m%d}c.txt"

    def _download_sftp(self, dates: list[date]) -> tuple[date, bytes]:
        import paramiko

        sock = socket.create_connection(
            (self.host, int(self.config.get("sftp_port", 22))),
            timeout=float(self.config.get("connect_timeout_seconds", 20)),
        )
        transport = paramiko.Transport(sock)
        try:
            transport.connect(username=self.username, password=self.password)
            sftp = paramiko.SFTPClient.from_transport(transport)
            try:
                for candidate in dates:
                    try:
                        with sftp.open(self._path(candidate), "rb") as handle:
                            return candidate, handle.read()
                    except OSError:
                        continue
            finally:
                sftp.close()
        finally:
            transport.close()
        raise FileNotFoundError("no recent daily corporate file found over SFTP")

    def _download_ftps(self, dates: list[date]) -> tuple[date, bytes]:
        ftp = ftplib.FTP_TLS(timeout=float(self.config.get("connect_timeout_seconds", 20)))
        ftp.connect(self.host, int(self.config.get("ftps_port", 21)))
        ftp.login(self.username, self.password)
        ftp.prot_p()
        try:
            for candidate in dates:
                buffer = io.BytesIO()
                try:
                    ftp.retrbinary(f"RETR {self._path(candidate)}", buffer.write)
                    return candidate, buffer.getvalue()
                except ftplib.error_perm as exc:
                    if not str(exc).startswith("550"):
                        raise
        finally:
            try:
                ftp.quit()
            except OSError:
                ftp.close()
        raise FileNotFoundError("no recent daily corporate file found over FTPS")

    def _download_https(self, dates: list[date]) -> tuple[date, bytes]:
        for candidate in dates:
            url = f"https://{self.host}/{self._path(candidate)}"
            response = self.session.get(
                url,
                auth=(self.username, self.password),
                timeout=float(self.config.get("https_timeout_seconds", 45)),
            )
            if response.status_code == 404:
                continue
            response.raise_for_status()
            return candidate, response.content
        raise FileNotFoundError("no recent daily corporate file found over HTTPS")
