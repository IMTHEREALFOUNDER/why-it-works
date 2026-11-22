"""Read-only VK setup probe. Never publish, upload, or print credentials."""
import datetime as dt
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

GROUP_ID = 243598472
VERSION = "5.199"

def call(method, token, **params):
    data = urllib.parse.urlencode({
        **params, "access_token": token, "v": VERSION
    }).encode()
    req = urllib.request.Request(
        "https://api.vk.com/method/" + method, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        return {"status": "http_error", "http_status": exc.code}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return {"status": "network_or_response_error"}
    if not isinstance(body, dict):
        return {"status": "invalid_response"}
    if "error" in body:
        # VK error payloads may echo request parameters. Never log them.
        code = body["error"].get("error_code") if isinstance(body["error"], dict) else None
        return {"status": "vk_error", "error_code": code if isinstance(code, int) else None}
    if "response" not in body:
        return {"status": "invalid_response"}
    return {"status": "ok", "response": body["response"]}

def probe(token):
    report = {
        "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "group_id": GROUP_ID,
        "read_only": True,
        "checks": {},
        "video_upload": "not_tested_requires_separate_access",
        "wall_write": "not_tested_read_only_probe",
        "autopublishing": "not_enabled",
    }
    if not token:
        report["checks"]["secret"] = {"status": "missing"}
        return report, False
    report["checks"]["secret"] = {"status": "present"}
    info = call("groups.getById", token, group_ids=str(GROUP_ID))
    check = {k: v for k, v in info.items() if k != "response"}
    if info["status"] == "ok":
        rows = info["response"]
        if isinstance(rows, dict):
            rows = rows.get("groups", [])
        matches = isinstance(rows, list) and any(
            isinstance(row, dict) and str(row.get("id")) == str(GROUP_ID) for row in rows)
        if not matches:
            check["status"] = "unexpected_group_response"
    report["checks"]["group_read"] = check
    wall = call("wall.get", token, owner_id=-GROUP_ID, count=1)
    wall_check = {k: v for k, v in wall.items() if k != "response"}
    if wall["status"] == "ok" and not isinstance(wall["response"], dict):
        wall_check["status"] = "unexpected_wall_response"
    report["checks"]["wall_read"] = wall_check
    ok = all(row["status"] in ("present", "ok") for row in report["checks"].values())
    return report, ok

def main():
    report, ok = probe(os.environ.get("VK_GROUP_TOKEN", "").strip())
    out = Path("reports")
    out.mkdir(exist_ok=True)
    (out / "vk-connection.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# VK connection check", "", "Community: 243598472", "",
             "| Check | Result |", "|---|---|"]
    for name, value in report["checks"].items():
        detail = value["status"]
        if "error_code" in value:
            detail += " (VK code: " + str(value["error_code"]) + ")"
        if "http_status" in value:
            detail += " (HTTP: " + str(value["http_status"]) + ")"
        lines.append("| " + name + " | " + detail + " |")
    lines += ["", "This check does not publish content.",
              "Wall write and video upload have NOT been verified.",
              "Autopublishing is NOT enabled."]
    summary = "\n".join(lines) + "\n"
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write(summary)
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
