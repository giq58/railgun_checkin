import os
import requests
import sys

# ======================
#  读取环境变量
# ======================
GLADOS_COOKIES     = os.getenv("GLADOS", "").strip()        # 多账号用换行分隔
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "").strip()

UA = "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0)"

CHECKIN_URL = "https://railgun.info/api/user/checkin"
STATUS_URL  = "https://railgun.info/api/user/status"
REFERER     = "https://railgun.info/console/checkin"

# 视为"签到流程正常结束"的关键词（包括重复签到）
SUCCESS_KEYWORDS = [
    "Checkin! Got",
    "Checkin Repeats! Please Try Tomorrow",
    "Today's observation logged. Return tomorrow for more points.",
]


# ======================
#  Telegram 通知
# ======================
def send_telegram(text: str) -> None:
    """向 Telegram 发送消息，失败时仅打印警告，不影响主流程。"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TG] 未配置 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID，跳过通知")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",          # 支持 <b> <i> <code> 等标签
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        print("[TG] 消息发送成功")
    except Exception as e:
        print(f"[TG] 消息发送失败（不影响签到结果）: {e}")


# ======================
#  签到主逻辑
# ======================
def glados_checkin():
    if not GLADOS_COOKIES:
        msg = "⚠️ 未设置 GLADOS 环境变量，跳过签到"
        print(msg)
        send_telegram(msg)
        return

    cookies_list = [c.strip() for c in GLADOS_COOKIES.split("\n") if c.strip()]

    has_real_error = False
    # 收集每个账号的结果，最后汇总发送
    summary_lines: list[str] = ["<b>🚀 Railgun 签到报告</b>"]

    for idx, cookie in enumerate(cookies_list, 1):
        print(f"\n===== 账号 {idx} =====")
        summary_lines.append(f"\n<b>账号 {idx}</b>")

        headers = {
            "cookie": cookie,
            "referer": REFERER,
            "user-agent": UA,
            "content-type": "application/json",
        }

        try:
            # ── 1. 签到 ──────────────────────────────────────────
            checkin_resp = requests.post(
                CHECKIN_URL,
                headers=headers,
                json={"token": "railgun.info"},
                timeout=15,
            )
            checkin_resp.raise_for_status()
            action = checkin_resp.json()

            message = action.get("message", "").strip()
            code    = action.get("code")

            print(f"签到返回 code={code} | message={message}")

            is_success = code == 0 or any(kw in message for kw in SUCCESS_KEYWORDS)

            if not is_success:
                raise ValueError(f"签到失败（非重复）: code={code} message={message}")

            # ── 2. 获取剩余天数 ───────────────────────────────────
            try:
                status_resp = requests.get(STATUS_URL, headers=headers, timeout=10)
                status_resp.raise_for_status()
                status = status_resp.json()

                left_days = status.get("data", {}).get("leftDays", "未知")
                if isinstance(left_days, (int, float)):
                    left_days = f"{float(left_days):.2f}"

                print(f"签到结果: {message}")
                print(f"剩余天数: {left_days}")

                summary_lines.append(f"✅ {message}")
                summary_lines.append(f"⏳ 剩余天数: <code>{left_days}</code>")

            except Exception as e:
                print(f"获取状态失败，但签到已算正常: {e}")
                summary_lines.append(f"✅ {message}")
                summary_lines.append(f"⚠️ 获取状态失败: {e}")

        except requests.exceptions.RequestException as e:
            err = f"网络请求失败: {e}"
            print(err)
            summary_lines.append(f"❌ {err}")
            has_real_error = True

        except ValueError as e:
            err = f"签到异常: {e}"
            print(err)
            summary_lines.append(f"❌ {err}")
            has_real_error = True

        except Exception as e:
            err = f"其他错误: {type(e).__name__}: {e}"
            print(err)
            summary_lines.append(f"❌ {err}")
            has_real_error = True

    # ── 汇总通知 ─────────────────────────────────────────────────
    if has_real_error:
        summary_lines.append("\n🔴 <b>存在账号签到失败，请检查日志！</b>")
    else:
        summary_lines.append("\n🟢 <b>所有账号签到流程正常结束</b>")

    send_telegram("\n".join(summary_lines))

    if has_real_error:
        print("\n存在至少一个账号签到真正失败 → 设置退出码 1 以触发通知")
        sys.exit(1)
    else:
        print("\n签到成功！所有账号签到流程正常结束")
        sys.exit(0)


def main():
    glados_checkin()


if __name__ == "__main__":
    main()
