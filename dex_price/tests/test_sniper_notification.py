#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 Sniper 通知 - 验证 CA 代码块格式
"""

import sys
import os
import io
import asyncio

# 修复 Windows GBK 编码
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.notifier import NotificationService
from config.settings import TelegramConfig, FeishuConfig


async def test_sniper_notification():
    """发送测试通知"""
    # 从配置加载
    import json
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(project_root, 'config', 'email.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    sniper_config = config.get('telegram_sniper', {})
    feishu_sniper_config = config.get('feishu_sniper', {})
    
    # 创建配置对象
    telegram_cfg = TelegramConfig(
        telegram_bot_token=sniper_config.get('telegram_bot_token'),
        telegram_chat_id=sniper_config.get('telegram_chat_id'),
        connect_timeout=sniper_config.get('connect_timeout', 90.0),
        read_timeout=sniper_config.get('read_timeout', 90.0),
    )
    
    feishu_cfg = FeishuConfig(
        webhook_url=feishu_sniper_config.get('webhook_url', '')
    )
    
    # 创建通知服务
    notifier = NotificationService(
        email_config=None,
        telegram_config=telegram_cfg,
        feishu_config=feishu_cfg,
    )
    
    # 测试 CA (代码块格式)
    test_ca = "Dfh5DzRgSvvCFDoYc2ciTkMrbDfRKybA4SoFbPmApump"
    
    # 发送测试通知 - 止盈止损格式
    test_msg = (
        f"🎉 【策略H TAKE_PROFIT_1.5x】TestToken\n"
        f"CA: <code>{test_ca}</code>\n"
        f"PNL: +0.1500 SOL (+50.0%)\n"
        f"💵 余额: 98.42 SOL"
    )
    
    print("正在发送测试通知 (止盈止损格式)...")
    await notifier.send_raw_message(test_msg)
    print("✅ 测试通知已发送，请查看 Telegram 和飞书!")


if __name__ == "__main__":
    asyncio.run(test_sniper_notification())
