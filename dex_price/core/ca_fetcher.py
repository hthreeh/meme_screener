"""
DEX 价格监控 - CA 获取模块
通过无头浏览器从代币详情页获取合约地址
"""

import logging
import time
from typing import Optional

from DrissionPage import Chromium, ChromiumOptions

_logger = logging.getLogger(__name__)


class CAFetcher:
    """
    代币合约地址获取器
    
    使用无头浏览器访问 DexScreener 代币详情页，
    从页面元素中提取代币的合约地址(CA)
    """
    
    BASE_URL = "https://dexscreener.com"
    
    # 页面加载配置
    PAGE_LOAD_WAIT = 3.0
    MAX_RETRIES = 2
    
    # CA 元素选择器
    CA_SELECTOR = "span[title]"
    CA_CLASS_PATTERN = "chakra-text"
    
    def __init__(self, headless: bool = True):
        """
        初始化 CA 获取器
        
        参数:
            headless: 是否使用无头模式（默认 True）
        """
        self.headless = headless
        self._browser = None
        self._logger = logging.getLogger(__name__)
    
    def _get_browser(self) -> Chromium:
        """获取或创建浏览器实例"""
        if self._browser is None:
            options = ChromiumOptions()
            if self.headless:
                options.headless()
            options.set_argument('--disable-gpu')
            options.set_argument('--no-sandbox')
            options.set_argument('--disable-dev-shm-usage')
            self._browser = Chromium(options)
        return self._browser
    
    def get_ca(self, href: str) -> Optional[str]:
        """
        从代币详情页获取合约地址
        
        参数:
            href: 代币相对路径（如 /solana/xxx）
            
        返回:
            合约地址字符串，失败返回 None
        """
        url = f"{self.BASE_URL}{href}"
        
        for attempt in range(self.MAX_RETRIES):
            try:
                self._logger.debug(f"获取 CA: {url} (尝试 {attempt + 1})")
                
                browser = self._get_browser()
                tab = browser.new_tab()
                
                try:
                    tab.get(url)
                    time.sleep(self.PAGE_LOAD_WAIT)
                    
                    # 查找包含 CA 的元素
                    ca = self._extract_ca_from_page(tab)
                    
                    if ca:
                        self._logger.info(f"成功获取 CA: {ca[:20]}...")
                        return ca
                    else:
                        self._logger.warning(f"未找到 CA 元素: {href}")
                        
                finally:
                    tab.close()
                    
            except Exception as e:
                self._logger.error(f"获取 CA 失败 (尝试 {attempt + 1}): {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(1)
        
        return None
    
    def _extract_ca_from_page(self, tab) -> Optional[str]:
        """
        从页面中提取 CA
        
        参数:
            tab: 浏览器标签页
            
        返回:
            CA 字符串
        """
        try:
            # 方法1: 查找代币信息区域的 CA
            # 代币地址通常在一个可点击的复制区域
            selectors_to_try = [
                # 主要选择器：token info 区域
                '.chakra-text.custom-72rvq0',
                'div[class*="custom-72rvq0"]',
                # 带 title 属性的 span（CA 完整地址在 title 里）
                'span[title]',
                # 带复制按钮的区域
                'button[aria-label*="Copy"]',
            ]
            
            for selector in selectors_to_try:
                elements = tab.eles(selector)
                for ele in elements:
                    # 尝试从 title 属性获取
                    title = ele.attr('title')
                    if title and self._is_valid_solana_address(title):
                        # 验证长度合适（排除 pair address）
                        if 40 <= len(title) <= 50:
                            return title
                    
                    # 尝试从文本内容获取
                    text = ele.text
                    if text and self._is_valid_solana_address(text):
                        if 40 <= len(text) <= 50:
                            return text
            
            # 方法2: 从页面 HTML 中搜索
            html = tab.html
            import re
            # 搜索 Solana 地址格式
            pattern = r'[1-9A-HJ-NP-Za-km-z]{43,44}'
            matches = re.findall(pattern, html)
            
            # 过滤掉 pair address（通常在 URL 中）
            current_url = tab.url
            url_address = None
            if '/solana/' in current_url:
                parts = current_url.split('/solana/')
                if len(parts) > 1:
                    url_address = parts[1].split('?')[0].split('#')[0].lower()
            
            for match in matches:
                # 验证格式
                if self._is_valid_solana_address(match):
                    # 排除 URL 中的 pair address
                    if url_address and match.lower() == url_address:
                        continue
                    return match
            
            return None
            
        except Exception as e:
            self._logger.error(f"提取 CA 时出错: {e}")
            return None
    
    def _is_valid_solana_address(self, address: str) -> bool:
        """
        验证是否为有效的 Solana 地址格式
        
        参数:
            address: 待验证的地址
            
        返回:
            是否有效
        """
        if not address:
            return False
        
        # Solana 地址是 base58 编码，长度通常为 32-44 个字符
        if len(address) < 32 or len(address) > 50:
            return False
        
        # Base58 不包含 0, O, I, l
        valid_chars = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
        return all(c in valid_chars for c in address)
    
    def get_ca_batch(self, hrefs: list) -> dict:
        """
        批量获取多个代币的 CA
        
        参数:
            hrefs: 代币 href 列表
            
        返回:
            href -> CA 的映射字典
        """
        results = {}
        
        for href in hrefs:
            ca = self.get_ca(href)
            if ca:
                results[href] = ca
            time.sleep(0.5)  # 避免请求过快
        
        self._logger.info(f"批量获取完成: {len(results)}/{len(hrefs)} 成功")
        return results
    
    def close(self):
        """关闭浏览器"""
        if self._browser:
            try:
                self._browser.quit()
            except Exception as e:
                self._logger.warning(f"关闭浏览器时出错: {e}")
            self._browser = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
