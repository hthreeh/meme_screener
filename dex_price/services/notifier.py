"""
DEX 价格监控 - 通知服务模块
处理 Telegram 和飞书通知
邮件通知已禁用
"""

import asyncio
import logging
import requests
# import smtplib  # 邮件功能已禁用
# from email.mime.text import MIMEText
# from email.mime.multipart import MIMEMultipart
from typing import List, Optional

import telegram
from telegram.request import HTTPXRequest

from config.settings import EmailConfig, TelegramConfig, FeishuConfig
from models.currency import Alert

# 专用日志器
_scanner_logger = logging.getLogger('scanner')  # Scanner 通知消息记录


class NotificationService:
    """
    统一通知服务，支持 Telegram 和飞书

    提供多渠道发送告警的方法，为每个渠道提供适当的格式化
    邮件通知功能已禁用
    """

    # Telegram 消息长度限制
    TELEGRAM_MAX_LENGTH = 4096
    TELEGRAM_CHUNK_SIZE = 5  # 每条消息包含的告警数

    # 飞书消息长度限制
    FEISHU_MAX_LENGTH = 20000
    FEISHU_CHUNK_SIZE = 10  # 每条消息包含的告警数

    def __init__(self, email_config: Optional[EmailConfig],
                 telegram_config: Optional[TelegramConfig],
                 feishu_config: Optional[FeishuConfig] = None):
        """
        初始化通知服务

        参数:
            email_config: 邮件配置（已禁用，可为 None）
            telegram_config: Telegram 配置
            feishu_config: 飞书配置
        """
        self.email_config = email_config
        self.telegram_config = telegram_config
        self.feishu_config = feishu_config
        self._logger = logging.getLogger(__name__)

    async def send_all(self, alerts: List[Alert], cycle_count: int,
                       timestamp: str) -> None:
        """
        通过所有已配置的渠道发送告警

        参数:
            alerts: 价格变化告警列表
            cycle_count: 当前监控周期数
            timestamp: 格式化的时间戳字符串
        """
        if not alerts:
            return

        # 发送 Telegram
        if self.telegram_config:
            telegram_messages = self._build_telegram_messages(alerts, cycle_count, timestamp)
            for msg in telegram_messages:
                await self._send_telegram(msg)
                await asyncio.sleep(0.5)  # 频率限制

        # 发送飞书
        if self.feishu_config:
            feishu_messages = self._build_feishu_messages(alerts, cycle_count, timestamp)
            for msg in feishu_messages:
                # 记录到 scanner 日志
                _scanner_logger.info(f"第{cycle_count}轮\n{msg}")
                self._send_feishu(msg)

        # 邮件通知已禁用
        # if self.email_config:
        #     email_html = self._build_email_html(alerts, timestamp)
        #     self._send_email("DEX 价格监控通知", email_html)

    def send_error_notification(self, error_message: str, subject: str = "【严重错误】DEX监控程序") -> None:
        """
        通过所有渠道发送错误通知

        参数:
            error_message: 错误描述
            subject: 邮件主题
        """
        if self.telegram_config:
            asyncio.run(self._send_telegram(f"⚠️ {error_message}"))

        if self.feishu_config:
            self._send_feishu(f"⚠️ {subject}\n\n{error_message}")

        # 邮件通知已禁用
        # if self.email_config:
        #     self._send_email(subject, error_message)

    async def send_raw_message(self, message: str) -> bool:
        """
        发送原始消息（用于 Sniper 通道）
        优先发送到 Telegram，同时也发送到飞书
        """
        success = False
        
        # 发送 Telegram
        if self.telegram_config:
            try:
                # 尝试将其视为 HTML 发送，如果失败则作为纯文本发送
                formatted_msg = message.replace('\n', '\n')
                await self._send_telegram(formatted_msg)
                success = True
            except Exception as e:
                self._logger.error(f"Sniper Telegram 发送失败: {e}")
        
        # 发送飞书
        if self.feishu_config:
            try:
                self._send_feishu(message)
                success = True
            except Exception as e:
                self._logger.error(f"Sniper 飞书发送失败: {e}")
        
        return success

    def _send_feishu(self, message: str) -> bool:
        """
        发送飞书消息

        参数:
            message: 纯文本消息

        返回:
            发送成功返回 True
        """
        if not self.feishu_config:
            self._logger.warning("飞书未配置")
            return False

        try:
            webhook_url = self.feishu_config.webhook_url
            
            payload = {
                "msg_type": "text",
                "content": {
                    "text": message
                }
            }

            headers = {
                "Content-Type": "application/json"
            }

            response = requests.post(
                webhook_url,
                json=payload,
                headers=headers,
                timeout=30
            )

            result = response.json()
            if result.get("code") == 0 or result.get("StatusCode") == 0:
                self._logger.info("飞书消息发送成功")
                return True
            else:
                self._logger.error(f"飞书消息发送失败: {result}")
                return False

        except Exception as e:
            self._logger.error(f"发送飞书消息出错: {e}")
            return False

    async def _send_telegram(self, message: str, max_retries: int = 3) -> bool:
        """
        发送 Telegram 消息（带重试机制）

        参数:
            message: HTML 格式的消息
            max_retries: 最大重试次数

        返回:
            发送成功返回 True
        """
        if not self.telegram_config:
            self._logger.warning("Telegram 未配置")
            return False

        for attempt in range(max_retries):
            try:
                custom_request = HTTPXRequest(
                    connect_timeout=self.telegram_config.connect_timeout,
                    read_timeout=self.telegram_config.read_timeout,
                )
                bot = telegram.Bot(
                    token=self.telegram_config.telegram_bot_token,
                    request=custom_request
                )
                await bot.send_message(
                    chat_id=self.telegram_config.telegram_chat_id,
                    text=message,
                    parse_mode=telegram.constants.ParseMode.HTML
                )
                self._logger.info(f"Telegram 消息已发送至 {self.telegram_config.telegram_chat_id}")
                return True

            except telegram.error.TelegramError as e:
                self._logger.warning(f"Telegram 错误 (尝试 {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    continue
                self._logger.error(f"Telegram 发送失败，已重试 {max_retries} 次")
                return False
            except Exception as e:
                self._logger.warning(f"Telegram 连接错误 (尝试 {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    continue
                self._logger.error(f"Telegram 发送失败，已重试 {max_retries} 次")
                return False
        
        return False

    # 邮件发送功能已禁用
    # def _send_email(self, subject: str, body: str) -> bool:
    #     """发送邮件通知（已禁用）"""
    #     ...

    def _build_feishu_messages(self, alerts: List[Alert], cycle_count: int,
                                timestamp: str) -> List[str]:
        """构建飞书消息，如果过长则分片"""
        alert_texts = []

        for alert in alerts:
            rates = alert.currency.growth_rates.to_dict()
            text = (
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 {alert.currency.currency_name} 【{alert.period_name}】\n"
                f"📁 来源: {alert.currency.source_file}\n"
                f"🔗 https://dexscreener.com{alert.currency.href}\n\n"
                f"涨跌幅:\n"
                f"  5M: {rates.get('5M', 'N/A')}%  |  1H: {rates.get('1H', 'N/A')}%\n"
                f"  6H: {rates.get('6H', 'N/A')}%  |  24H: {rates.get('24H', 'N/A')}%\n\n"
                f"💰 上次市值: {alert.previous_value}\n"
                f"💰 本次市值: {alert.current_value}\n"
                f"🚀 涨幅: {alert.change_rate:.2f}% {alert.get_append_str()}\n\n"
                f"📝 CA: {alert.currency.contract_address}"
            )
            alert_texts.append(text)

        # 构建完整消息
        header = f"🔔 DEX 价格监控 (第 {cycle_count} 轮)\n⏰ {timestamp}\n"
        full_message = header + "\n\n".join(alert_texts)

        if len(full_message) <= self.FEISHU_MAX_LENGTH:
            return [full_message]

        # 分片
        messages = []
        for i in range(0, len(alert_texts), self.FEISHU_CHUNK_SIZE):
            chunk = alert_texts[i:i + self.FEISHU_CHUNK_SIZE]
            chunk_msg = f"🔔 DEX 监控 (分片 {i//self.FEISHU_CHUNK_SIZE + 1})\n\n" + "\n\n".join(chunk)
            messages.append(chunk_msg)

        return messages

    def _build_telegram_messages(self, alerts: List[Alert], cycle_count: int,
                                  timestamp: str) -> List[str]:
        """构建 Telegram 消息，如果过长则分片"""
        alert_texts = []

        for alert in alerts:
            rates = alert.currency.growth_rates.to_dict()
            text = (
                f"🗂<b>来源: {alert.currency.source_file}</b>\n"
                f"<b>📈 {alert.currency.currency_name} {alert.period_name}价格变化</b>\n\n"
                f"🔗 <a href='https://dexscreener.com{alert.currency.href}'>DexScreener 页面</a>\n\n"
                f"5M: <b>{rates.get('5M', 'N/A')}%</b>, 1H: <b>{rates.get('1H', 'N/A')}%</b>   "
                f"6H: <b>{rates.get('6H', 'N/A')}%</b>, 24H: <b>{rates.get('24H', 'N/A')}%</b>\n\n"
                f"💰上次市值: <code>{alert.previous_value}</code>\n"
                f"本次市值: <code>{alert.current_value}</code>\n\n"
                f"ca: <code>{alert.currency.contract_address}</code>\n"
                f"🚀涨幅: <b>{alert.change_rate:.2f}%</b> {alert.get_append_str()}\n"
                f"{'─' * 40}"
            )
            alert_texts.append(text)

        # 检查是否需要分片
        full_message = f"<b>DEX 价格监控 (第 {cycle_count} 轮)</b>\n\n"
        full_message += "\n\n".join(alert_texts)
        full_message += f"\n\n⏰ {timestamp}"

        if len(full_message) <= self.TELEGRAM_MAX_LENGTH:
            return [full_message]

        # 分片
        messages = []
        for i in range(0, len(alert_texts), self.TELEGRAM_CHUNK_SIZE):
            chunk = alert_texts[i:i + self.TELEGRAM_CHUNK_SIZE]
            chunk_msg = f"<b>DEX 监控 (分片)</b>\n" + "\n\n".join(chunk)
            messages.append(chunk_msg)

        return messages

    # 邮件 HTML 构建功能已禁用
    # def _build_email_html(self, alerts: List[Alert], timestamp: str) -> str:
    #     """构建 HTML 邮件正文"""
    #     ...
