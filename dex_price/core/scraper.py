"""
DEX 价格监控 - 页面抓取模块
处理与 DexScreener 页面的交互，提取数据
支持失败重试机制
"""

import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple, Set

from DrissionPage import ChromiumPage

from config.settings import AppSettings


class PageScraper:
    """
    从 DexScreener 页面抓取加密货币数据

    处理点击收藏夹项目、等待页面加载、保存 HTML 内容用于解析
    支持失败后重试机制
    """

    # 页面加载验证参数
    MAX_LOAD_WAIT_SECONDS = 10  # 最大等待时间
    LOAD_CHECK_INTERVAL = 0.5   # 检查间隔
    REQUIRED_MARKER = "ds-dex-table-row ds-dex-table-row-top"  # 数据加载完成的标记

    def __init__(self, settings: AppSettings, data_dir: Path):
        """
        初始化页面抓取器

        参数:
            settings: 应用程序配置
            data_dir: 保存 HTML 文件的目录
        """
        self.settings = settings
        self.data_dir = data_dir
        self._logger = logging.getLogger(__name__)

        # 确保数据目录存在
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def scrape_url(self, page: ChromiumPage, url_name: str, output_filename: str) -> Tuple[Path, bool]:
        """
        抓取收藏夹中指定 URL 的数据

        参数:
            page: 浏览器页面/标签页
            url_name: 收藏夹中的 URL 名称
            output_filename: 保存 HTML 内容的文件名

        返回:
            (保存的文件路径, 是否成功)
            如果数据加载失败，返回 (None, False)

        异常:
            ScraperError: 抓取过程中发生严重错误时抛出
        """
        output_path = self.data_dir / output_filename

        try:
            # 查找并点击收藏夹项目
            self._logger.debug(f"[{url_name}] 正在查找收藏夹项目...")
            parent = page.ele('.chakra-stack custom-1yxzmc7')
            item = parent.ele(f'text:{url_name}')
            item.click()
            
            # 等待页面初始响应
            time.sleep(self.settings.click_wait)

            # 点击市值列进行排序
            self._logger.debug(f"[{url_name}] 点击市值列排序...")
            page.ele('.ds-table-th ds-dex-table-th-market-cap').click()
            
            # 等待数据加载完成
            self._logger.debug(f"[{url_name}] 等待数据加载...")
            load_success = self._wait_for_data_load(page, url_name)
            
            if not load_success:
                self._logger.warning(f"[{url_name}] 数据加载超时，跳过此次抓取（等待重试）")
                return None, False

            # 保存页面内容
            content = page.html
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)

            # 验证保存的内容
            if self.REQUIRED_MARKER in content:
                row_count = content.count(self.REQUIRED_MARKER)
                self._logger.info(f"[{url_name}] 页面内容已保存，检测到 {row_count} 行数据")
                return output_path, True
            else:
                self._logger.warning(f"[{url_name}] 页面已保存但未检测到数据行标记！")
                return None, False

        except Exception as e:
            self._logger.error(f"[{url_name}] 抓取失败: {e}", exc_info=True)
            raise ScraperError(f"抓取 {url_name} 失败: {e}") from e

    def _wait_for_data_load(self, page: ChromiumPage, url_name: str) -> bool:
        """
        等待页面数据加载完成

        参数:
            page: 浏览器页面
            url_name: URL 名称（用于日志）

        返回:
            True 如果数据加载成功，False 如果超时
        """
        start_time = time.time()
        
        while time.time() - start_time < self.MAX_LOAD_WAIT_SECONDS:
            try:
                html = page.html
                
                # 检查是否包含数据行标记
                if self.REQUIRED_MARKER in html:
                    elapsed = time.time() - start_time
                    self._logger.debug(f"[{url_name}] 数据加载完成，耗时 {elapsed:.1f} 秒")
                    return True
                
                # 检查是否仍在加载
                if "Loading" in html or "请稍候" in html:
                    self._logger.debug(f"[{url_name}] 页面仍在加载中...")
                
            except Exception as e:
                self._logger.debug(f"[{url_name}] 检查加载状态时出错: {e}")
            
            time.sleep(self.LOAD_CHECK_INTERVAL)
        
        elapsed = time.time() - start_time
        self._logger.warning(f"[{url_name}] 等待数据加载超时 ({elapsed:.1f} 秒)")
        return False

    def scrape_chunk_with_retry(self, page: ChromiumPage, url_mapping_chunk: Dict[str, str]) -> Tuple[Dict[str, Path], Set[str]]:
        """
        在单个标签页上抓取多个 URL，返回成功的结果和失败的 URL 列表

        参数:
            page: 浏览器页面/标签页
            url_mapping_chunk: 要抓取的 URL 映射子集

        返回:
            (成功的 url_name -> 文件路径 字典, 失败的 url_name 集合)
        """
        results = {}
        failed_urls = set()

        for url_name, output_filename in url_mapping_chunk.items():
            try:
                output_path, success = self.scrape_url(page, url_name, output_filename)
                if success and output_path:
                    results[url_name] = output_path
                else:
                    failed_urls.add(url_name)
                    self._logger.info(f"[{url_name}] 首次抓取失败，将在稍后重试")
            except ScraperError as e:
                failed_urls.add(url_name)
                self._logger.warning(f"[{url_name}] 抓取出错，将在稍后重试: {e}")
            except Exception as e:
                failed_urls.add(url_name)
                self._logger.error(f"[{url_name}] 处理出错: {e}")

        return results, failed_urls

    def retry_failed_urls(self, page: ChromiumPage, failed_urls: Set[str], url_mapping: Dict[str, str]) -> Dict[str, Path]:
        """
        重试之前失败的 URL

        参数:
            page: 浏览器页面/标签页
            failed_urls: 失败的 url_name 集合
            url_mapping: 完整的 URL 映射

        返回:
            重试成功的 url_name -> 文件路径 字典
        """
        if not failed_urls:
            return {}

        self._logger.info(f"开始重试 {len(failed_urls)} 个失败的 URL: {failed_urls}")
        retry_results = {}

        for url_name in failed_urls:
            output_filename = url_mapping.get(url_name)
            if not output_filename:
                continue

            try:
                self._logger.info(f"[{url_name}] 第二次尝试抓取...")
                output_path, success = self.scrape_url(page, url_name, output_filename)
                if success and output_path:
                    retry_results[url_name] = output_path
                    self._logger.info(f"[{url_name}] 重试成功！")
                else:
                    self._logger.warning(f"[{url_name}] 第二次尝试仍然失败，放弃此 URL")
            except Exception as e:
                self._logger.error(f"[{url_name}] 重试时出错，放弃此 URL: {e}")

        return retry_results


class ScraperError(Exception):
    """抓取错误自定义异常"""
    pass
