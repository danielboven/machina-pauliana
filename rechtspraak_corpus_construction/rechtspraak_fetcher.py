#!/usr/bin/env python3
"""Fetch Rechtspraak uitspraken XML for dc_source rows (WooZM database dump)
from Postgres.

The script streams the SQL rows and extracts the ECLI from each dc_source URL.
Then downloads the corresponding content document into a court/year directory.
A shared rate limiter caps the request rate according per IVO Rechtspraak 2019.
"""

import argparse
import asyncio
import os
from urllib.parse import urlsplit, parse_qs, quote

import asyncpg
import httpx
from aiolimiter import AsyncLimiter
from tenacity import (
    retry,
    stop_after_attempt,
    retry_if_exception_type,
    RetryCallState,
)
from tqdm import tqdm

CONTENT_URL = "https://data.rechtspraak.nl/uitspraken/content?id={}"


class TransientError(Exception):
    """Failure, can be retried. It carries an optional server-requested wait."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def extract_ecli(dc_source: str) -> str:
    """Pull the ECLI from the 'id' query parameter of a dc_source URL."""
    ecli = parse_qs(urlsplit(dc_source).query).get("id", [""])[0]
    if not ecli:
        raise ValueError("missing id query parameter")
    if not ecli.upper().startswith("ECLI:"):
        raise ValueError(f"id is not an ECLI: {ecli!r}")
    return ecli


def build_path(root: str, ecli: str) -> str:
    """Map ECLI such as ECLI:NL:HR:1981:AG4158 to
    <root>/HR/1981/ECLI_NL_HR_1981_AG4158.xml."""
    parts = ecli.split(":")
    if len(parts) < 5:
        raise ValueError(f"unexpected ECLI format: {ecli!r}")
    return os.path.join(
        root, parts[2], parts[3], ecli.replace(":", "_") + ".xml"
    )


def _wait(state: RetryCallState) -> float:
    """Honor the server Retry-After header, otherwise do an exponential
    backoff."""
    exc = state.outcome.exception()
    if isinstance(exc, TransientError) and exc.retry_after is not None:
        return exc.retry_after
    return min(2**state.attempt_number, 10)


@retry(
    stop=stop_after_attempt(3),
    wait=_wait,
    retry=retry_if_exception_type((TransientError, httpx.TransportError)),
    reraise=True,
)
async def fetch_and_save(
    client: httpx.AsyncClient, limiter: AsyncLimiter, ecli: str, path: str
) -> None:
    """Download one document within rate limit and write the document."""
    async with limiter:
        resp = await client.get(CONTENT_URL.format(quote(ecli)))

    if resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After")
        raise TransientError(
            "rate limited by server",
            float(retry_after)
            if retry_after and retry_after.isdigit()
            else None,
        )
    if resp.status_code >= 500:
        raise TransientError(f"server error: {resp.status_code}")
    resp.raise_for_status()

    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(resp.content)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


async def worker(
    queue: asyncio.Queue,
    client: httpx.AsyncClient,
    limiter: AsyncLimiter,
    output_dir: str,
    pbar: tqdm,
    stats: dict,
) -> None:
    """Asynchronous worker that gets the dc_source from DB, gets the ECLI and
    calls fetch when XML file is not yet present on the disk."""
    while True:
        dc_source = await queue.get()
        if dc_source is None:
            queue.task_done()
            return
        try:
            ecli = extract_ecli(dc_source)
            path = build_path(output_dir, ecli)
            if os.path.exists(path):
                stats["skipped"] += 1
            else:
                await fetch_and_save(client, limiter, ecli, path)
        except Exception as e:
            tqdm.write(f"failed for dc_source={dc_source!r}: {e}")
            stats["failed"] += 1
        finally:
            queue.task_done()
            pbar.update(1)
            pbar.set_postfix(skipped=stats["skipped"], failed=stats["failed"])


async def run(args: argparse.Namespace) -> None:
    """Create DB connection, create queue, put rows in queue to be processed
    by worker."""
    limiter = AsyncLimiter(1, 1 / args.rate)
    queue: asyncio.Queue = asyncio.Queue(maxsize=args.concurrency * 2)

    timeout = httpx.Timeout(args.timeout, connect=10.0)
    conn = await asyncpg.connect(args.dsn)
    try:
        async with httpx.AsyncClient(timeout=timeout, http2=True) as client:
            total = await conn.fetchval(
                f"SELECT COUNT(*) FROM ({args.query}) AS _q"
            )
            stats = {"skipped": 0, "failed": 0}
            with tqdm(total=total, unit="file", desc="Fetching") as pbar:
                workers = [
                    asyncio.create_task(
                        worker(
                            queue, client, limiter, args.output_dir, pbar, stats
                        )
                    )
                    for _ in range(args.concurrency)
                ]
                async with conn.transaction():
                    async for record in conn.cursor(args.query):
                        await queue.put(record["dc_source"])
                for _ in workers:
                    await queue.put(None)
                await asyncio.gather(*workers)
    finally:
        await conn.close()


def main() -> None:
    """Main CLI function that needs a Postgres connection, query returning the
    dc_source rows and the output (XML) directory at minimum."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", required=True, help="Postgres connection string")
    p.add_argument(
        "--query", required=True, help="SQL returning dc_source rows"
    )
    p.add_argument(
        "--output-dir", required=True, help="Root directory for XML output"
    )
    p.add_argument(
        "--rate", type=float, default=10.0, help="Max requests/sec (default 10)"
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="Concurrent fetchers (default 8)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-request timeout secs (default 30)",
    )
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
