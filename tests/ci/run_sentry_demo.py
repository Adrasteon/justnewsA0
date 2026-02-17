import os
import time


def main():
    dsn = os.environ.get("SENTRY_DSN", "")
    if not dsn:
        print("SENTRY_DSN not set; skipping")
        return 0

    print("Initializing Sentry with DSN (will send a single demo event)")
    try:
        import sentry_sdk

        from common.sentry_integration import init_sentry

        ok = init_sentry("ci-demo", logger=None)
        if not ok:
            print("Failed to initialize Sentry")
            return 2

        # Send a demo event
        sentry_sdk.capture_message("JustNews demo event from CI")
        print("Sent demo event — waiting briefly for transport")
        time.sleep(2)
        print("Done")
        return 0

    except Exception as exc:  # pragma: no cover - only executed in manual run
        print("Error sending demo event:", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
