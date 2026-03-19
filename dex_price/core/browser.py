"""
DEX 价格监控 - 浏览器管理模块
封装 DrissionPage 浏览器操作
"""

import logging
import time
from typing import List, Optional

from DrissionPage import Chromium, ChromiumPage

from config.settings import AppSettings


class BrowserManager:
    """
    管理浏览器生命周期和多标签页并行抓取

    属性:
        settings: 应用程序配置
        browser: Chromium 浏览器实例
        tabs: 打开的浏览器标签页列表
    """

    def __init__(self, settings: AppSettings):
        """
        初始化浏览器管理器

        参数:
            settings: 应用程序配置
        """
        self.settings = settings
        self.browser: Optional[Chromium] = None
        self.tabs: List[ChromiumPage] = []
        self._logger = logging.getLogger(__name__)

    def start(self) -> None:
        """启动浏览器并打开初始标签页"""
        self._logger.info("正在启动浏览器...")
        self.browser = Chromium()

        for i in range(self.settings.num_pages):
            self._logger.info(f"正在打开标签页 {i + 1}/{self.settings.num_pages}...")
            tab = self._open_new_tab(self.settings.base_url)
            self.tabs.append(tab)

        self._logger.info(f"浏览器启动完成，共 {len(self.tabs)} 个标签页")

    def stop(self) -> None:
        """关闭所有标签页并停止浏览器"""
        self._logger.info("正在停止浏览器...")
        for tab in self.tabs:
            try:
                tab.close()
            except Exception as e:
                self._logger.warning(f"关闭标签页时出错: {e}")

        self.tabs.clear()

        if self.browser:
            try:
                self.browser.quit()
            except Exception as e:
                self._logger.warning(f"退出浏览器时出错: {e}")
            self.browser = None

        self._logger.info("浏览器已停止")

    def restart_tabs(self) -> None:
        """
        关闭并重新打开所有标签页
        用于防止长时间运行导致的内存泄漏
        """
        self._logger.info("正在重启所有浏览器标签页...")

        # 关闭现有标签页
        for tab in self.tabs:
            try:
                tab.close()
            except Exception as e:
                self._logger.warning(f"重启时关闭标签页出错: {e}")

        self.tabs.clear()

        # 重新打开标签页
        if self.browser is None:
            raise RuntimeError("浏览器未初始化，请先调用 start()")

        for i in range(self.settings.num_pages):
            self._logger.info(f"正在重新打开标签页 {i + 1}/{self.settings.num_pages}...")
            tab = self._open_new_tab(self.settings.base_url)
            self.tabs.append(tab)

        self._logger.info("所有标签页重启成功")

    def clear_cookies_and_restart(self) -> None:
        """
        清除浏览器 cookies 并重启所有标签页
        用于应对反爬虫限制（当 API 正常但网页抓取失败时）
        """
        self._logger.warning("检测到反爬虫限制，正在清除 cookies 并重启标签页...")

        if self.browser is None:
            raise RuntimeError("浏览器未初始化，请先调用 start()")

        try:
            # 关闭现有标签页
            for tab in self.tabs:
                try:
                    tab.close()
                except Exception as e:
                    self._logger.warning(f"关闭标签页出错: {e}")
            self.tabs.clear()

            # 清除 cookies（使用浏览器的第一个标签页）
            temp_tab = self.browser.new_tab()
            temp_tab.get(self.settings.base_url)
            time.sleep(1)
            
            # DrissionPage 清除 cookies 的方式
            temp_tab.run_cdp('Network.clearBrowserCookies')
            temp_tab.run_cdp('Network.clearBrowserCache')
            self._logger.info("已清除浏览器 cookies 和缓存")
            
            temp_tab.close()
            time.sleep(1)

            # 重新打开标签页
            for i in range(self.settings.num_pages):
                self._logger.info(f"正在重新打开标签页 {i + 1}/{self.settings.num_pages}...")
                tab = self._open_new_tab(self.settings.base_url)
                self.tabs.append(tab)

            self._logger.info("反爬虫恢复完成：cookies 已清除，标签页已重启")

        except Exception as e:
            self._logger.error(f"清除 cookies 并重启失败: {e}", exc_info=True)
            # 回退到普通重启
            self.restart_tabs()

    def get_tabs(self) -> List[ChromiumPage]:
        """获取已打开的浏览器标签页列表"""
        return self.tabs

    def _open_new_tab(self, url: str) -> ChromiumPage:
        """
        打开一个新的浏览器标签页并导航到指定 URL

        参数:
            url: 要导航到的 URL

        返回:
            新的 ChromiumPage 标签页
        """
        if self.browser is None:
            raise RuntimeError("浏览器未初始化，请先调用 start()")

        tab = self.browser.new_tab()
        tab.get(url)
        time.sleep(self.settings.page_load_wait)
        return tab

    @property
    def is_running(self) -> bool:
        """检查浏览器是否正在运行"""
        return self.browser is not None and len(self.tabs) > 0
