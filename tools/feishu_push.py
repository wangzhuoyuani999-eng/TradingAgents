"""飞书主动推送（走 DSH-IM 的主动投递 HTTP 接口）。

为什么不用 `feishu_push(...)`：那是 skill 旧文档里的臆想工具，实际不存在。
DSH 的 IM 插件（`@xmanrui/dsh-im`）只提供 `POST /api/dsh-im/delivery/messages`，
参数是稳定的 `botId + targetId`，不依赖会话、不污染上下文。

用法（工作目录 = 仓库根）：

    .venv/Scripts/python.exe tools/feishu_push.py --label 盘中巡检 --text "600428 触发 A：11.20 ≤ 止损 10.45？否…"
    .venv/Scripts/python.exe tools/feishu_push.py --label 收盘总结 --text-file data/logs/summary.md --format markdown
    Get-Content msg.md -Raw | .venv/Scripts/python.exe tools/feishu_push.py --format markdown
    .venv/Scripts/python.exe tools/feishu_push.py --dry-run --text "只打印不发送"

约定：
- 默认 `--format markdown`（飞书侧渲染成原生 Markdown 卡片）；纯文本用 `--format plain`。
- 成功打印 `sent:true` 并返回 0；失败打印错误码 + 处理建议并返回 1。
- 飞书主动卡片**不会自动分段**，建议单条 ≤ 3000 字符；超长只告警，不自动截断。
- 机器人离线、目标被删、平台拒发都会返回明确错误码，调用方决定是否重试（本脚本不重试）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 机器人 / 投递目标的 ID 属于个人环境信息，**不写进仓库**。
# 取值顺序：环境变量 > tools/.feishu_targets.json（本地，已被 .gitignore 忽略）
LOCAL_TARGETS = Path(__file__).resolve().parent / ".feishu_targets.json"
DEFAULT_TARGET = "group"
PATH = "/api/dsh-im/delivery/messages"
SOFT_LIMIT = 3000

HINTS = {
    "bad-request": "请求结构或文字无效：检查 --text 是否为空、字段名是否被改动",
    "unknown-bot": "botId 不属于当前 Host：从「设置 → IM机器人」重新复制 Bot ID",
    "unknown-target": "targetId 不存在或已删除：检查目标别名，必要时重建投递目标",
    "target-conflict": "同一机器人下 targetId 重复",
    "invalid-target": "目标类型或平台原生 ID 不符合渠道规则",
    "bot-not-connected": "机器人当前离线：等它恢复连接后再发，不要盲目重试",
    "target-rejected": "平台明确拒发：检查飞书应用权限与目标 ID",
    "delivery-failed": "网络/平台发送失败：看 Host 日志，不要重复轰炸",
}


def base_url(explicit: str = "") -> str:
    if explicit:
        return explicit.rstrip("/")
    for name in ("DSH_WEB_URL", "FEISHU_PUSH_BASE"):
        value = os.environ.get(name)
        if value:
            return value.rstrip("/")
    return "http://127.0.0.1:55456"


def resolve_text(args) -> str:
    if args.text:
        return args.text
    if args.text_file:
        return Path(args.text_file).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def decorate(text: str, label: str, fmt: str) -> str:
    if not label:
        return text
    if fmt == "markdown":
        return f"**【{label}】**\n\n{text}"
    return f"【{label}】\n{text}"


def load_targets() -> tuple[str, dict[str, str]]:
    """返回 (botId, {别名: targetId})；环境变量优先，其次本地 JSON。"""
    bot = os.environ.get("FEISHU_BOT_ID", "")
    targets: dict[str, str] = {}
    if LOCAL_TARGETS.exists():
        try:
            cfg = json.loads(LOCAL_TARGETS.read_text(encoding="utf-8"))
            bot = bot or str(cfg.get("botId") or "")
            for k, v in (cfg.get("targets") or {}).items():
                if isinstance(v, str) and v:
                    targets[k] = v
        except Exception as exc:  # noqa: BLE001
            print(f"[!] 读取 {LOCAL_TARGETS.name} 失败：{exc}", file=sys.stderr)
    for alias, env in (("group", "FEISHU_TARGET_GROUP"), ("private", "FEISHU_TARGET_PRIVATE")):
        if os.environ.get(env):
            targets[alias] = os.environ[env]
    return bot, targets


def main() -> int:
    # Windows 控制台默认 GBK，打印 ⚠️/中文会 UnicodeEncodeError；统一转 UTF-8 输出
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="飞书主动推送（DSH-IM 主动投递）")
    ap.add_argument("--text", default="", help="要发送的文字；留空则读 --text-file 或 stdin")
    ap.add_argument("--text-file", default="", help="从文件读取正文（UTF-8）")
    ap.add_argument("--label", default="", help="标题前缀，如 盘中巡检 / 收盘总结 / 收盘定池")
    ap.add_argument("--to", default=DEFAULT_TARGET,
                    help="投递目标：group（默认，交易台群）/ private（私聊）/ 或直接给 targetId")
    ap.add_argument("--action", action="append", default=[],
                    help="需要用户真正执行的操作；可重复。有它就在消息最上方生成醒目高亮块")
    ap.add_argument("--format", choices=("markdown", "plain"), default="markdown")
    ap.add_argument("--dry-run", action="store_true", help="只打印 payload，不发送")
    ap.add_argument("--base", default="", help="Host 地址，默认取 $env:DSH_WEB_URL")
    ap.add_argument("--timeout", type=float, default=15.0)
    args = ap.parse_args()

    text = decorate(resolve_text(args).strip(), args.label.strip(), args.format)
    if not text:
        print("[x] 空消息，不发送", file=sys.stderr)
        return 2

    # 需要用户动手的部分放在最前面，加粗成块，避免被正文淹没
    actions = [a.strip() for a in args.action if a and a.strip()]
    if actions:
        if args.format == "markdown":
            head = ["**⚠️ 需要你操作**", ""]
            head += ([f"**{actions[0]}**"] if len(actions) == 1
                     else [f"**{i}. {a}**" for i, a in enumerate(actions, 1)])
            text = "\n".join(head) + "\n\n---\n\n" + text
        else:
            head = ["【⚠️ 需要你操作】"]
            head += ([f"* {actions[0]}"] if len(actions) == 1
                     else [f"{i}. {a}" for i, a in enumerate(actions, 1)])
            text = "\n".join(head) + "\n----------\n" + text
    if len(text) > SOFT_LIMIT:
        print(f"[!] 正文 {len(text)} 字符，超过建议上限 {SOFT_LIMIT}；飞书主动卡片不自动分段，可能被平台拒绝",
              file=sys.stderr)

    bot_id, targets = load_targets()
    if not bot_id or not targets:
        print(f"[x] 缺少飞书配置：请在 {LOCAL_TARGETS} 里填 botId / targets，"
              f"或设置环境变量 FEISHU_BOT_ID / FEISHU_TARGET_GROUP / FEISHU_TARGET_PRIVATE", file=sys.stderr)
        return 2
    payload = {
        "botId": bot_id,
        "targetId": targets.get(args.to, args.to),
        "text": text,
        "format": args.format,
    }
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    url = base_url(args.base) + PATH
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        code = "http-" + str(exc.code)
        try:
            code = json.loads(body)["error"]["code"]
        except Exception:
            pass
        print(f"[x] 推送失败 code={code} :: {body}", file=sys.stderr)
        if code in HINTS:
            print(f"    建议：{HINTS[code]}", file=sys.stderr)
        return 1
    except Exception as exc:  # 连接失败 / 超时
        print(f"[x] 无法连接 {url}：{exc}", file=sys.stderr)
        print("    建议：确认 DSH 客户端在运行；$env:DSH_WEB_URL 指向当前 Host 地址", file=sys.stderr)
        return 1

    try:
        result = json.loads(body)
    except Exception:
        print(f"[x] 返回无法解析：{body}", file=sys.stderr)
        return 1
    if result.get("sent") is True:
        print(f"sent:true  ({len(text)} 字符 → {payload['targetId']})")
        return 0
    print(f"[x] 未确认发送：{body}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
