"""Replay the load scenario: 200 sequential GET /users requests."""

import httpx

BASE_URL = "http://127.0.0.1:8000"
REQUEST_COUNT = 200


def main() -> None:
    errors = 0
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        for _ in range(REQUEST_COUNT):
            response = client.get("/users")
            if response.status_code >= 400:
                errors += 1
    print(f"done: {REQUEST_COUNT} requests, {errors} errors")


if __name__ == "__main__":
    main()
