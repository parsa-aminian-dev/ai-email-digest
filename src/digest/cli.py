from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta

from src.digest.config.settings import Settings
from src.digest.logging import configure_logging
from src.digest.service import DigestService


def main() -> None:
    parser = argparse.ArgumentParser(description="Privacy-first daily email digests")
    parser.add_argument(
        "command",
        nargs="?",
        choices=[
            "demo",
            "ingest",
            "digest",
            "run",
            "cleanup",
            "purge",
            "delivery-status",
            "resolve-delivery",
        ],
    )
    parser.add_argument("--demo", action="store_true", help="Alias for demo")
    parser.add_argument("--purge", action="store_true", help="Alias for purge")
    parser.add_argument(
        "--deliver", action="store_true", help="Deliver a digest to the configured owner"
    )
    parser.add_argument("--start", type=datetime.fromisoformat)
    parser.add_argument("--end", type=datetime.fromisoformat)
    parser.add_argument("--id", help="Digest ID for delivery reconciliation")
    parser.add_argument(
        "--state", choices=["sent", "pending"], help="Mark sent, or explicitly allow a resend"
    )
    args = parser.parse_args()
    command = args.command or ("demo" if args.demo else "purge" if args.purge else None)
    if not command:
        parser.print_help()
        return
    settings = Settings()
    if command == "demo":
        settings = settings.model_copy(update={"demo_mode": True})
    configure_logging(settings.log_level)
    service = None
    try:
        service = DigestService(
            settings, initialize_integrations=command in {"demo", "ingest", "digest", "run"}
        )
        if command == "demo":
            service.ingest()
            now = datetime.now(UTC)
            result = service.generate_digest(now - timedelta(days=1), now, deliver=True)
            print(result.text)
            print(f"HTML preview: {settings.output_dir}/{result.id}.html")
        elif command == "ingest":
            print(json.dumps(service.ingest(), indent=2))
        elif command == "digest":
            if any(value and value.tzinfo is None for value in (args.start, args.end)):
                raise ValueError("Use timezone-aware start/end dates")
            result = service.generate_digest(args.start, args.end, deliver=args.deliver)
            print(result.model_dump_json(indent=2))
        elif command == "run":
            print(json.dumps(service.run_scheduled(), indent=2))
        elif command == "cleanup":
            count = service.repository.cleanup(service.config.retention_days)
            service.cleanup_previews()
            print(f"Deleted {count} expired records.")
        elif command == "purge":
            service.purge()
            print("Stored metadata, checkpoints, delivery history and previews purged.")
        elif command in {"delivery-status", "resolve-delivery"}:
            if not args.id:
                raise ValueError("--id is required")
            state = service.repository.delivery_state(args.id)
            if state is None:
                raise ValueError("Unknown digest ID")
            if command == "resolve-delivery":
                if not args.state:
                    raise ValueError("--state is required after checking the SMTP recipient inbox")
                service.repository.mark_delivery(args.id, args.state)
                state = args.state
            print(f"{args.id}: {state}")
    except Exception as error:
        print(
            f"Command failed ({type(error).__name__}); check configuration and delivery status.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    finally:
        if service:
            service.close()


if __name__ == "__main__":
    main()
