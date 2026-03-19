"""
检查 HTML 文件的内容特征
"""

import re
import sys
from pathlib import Path

# 设置控制台输出编码
sys.stdout.reconfigure(encoding='utf-8')


def check_html_content(file_path: str):
    """检查 HTML 文件的内容"""
    
    print(f"\n{'='*60}")
    print(f"检查文件: {file_path}")
    print(f"{'='*60}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"文件大小: {len(content)} 字符")
    
    # 检查是否包含 "请稍候" 或其他加载提示
    if "请稍候" in content:
        print("[警告] 包含 '请稍候' - 页面可能未完全加载")
    
    if "Loading" in content:
        print("[警告] 包含 'Loading' - 页面可能未完全加载")
    
    # 检查核心内容标记
    if "ds-dex-table-row ds-dex-table-row-top" in content:
        count = content.count("ds-dex-table-row ds-dex-table-row-top")
        print(f"[OK] 包含表格行标记 'ds-dex-table-row ds-dex-table-row-top': {count} 次")
    else:
        print("[错误] 不包含表格行标记 'ds-dex-table-row ds-dex-table-row-top'")
    
    # 检查是否包含 href 链接
    href_pattern = r'href="/solana/[a-zA-Z0-9]+'
    href_matches = re.findall(href_pattern, content)
    print(f"包含 Solana 链接: {len(href_matches)} 个")
    
    # 检查是否包含市值数据
    if "ds-dex-table-row-col-market-cap" in content:
        count = content.count("ds-dex-table-row-col-market-cap")
        print(f"[OK] 包含市值列: {count} 次")
    else:
        print("[错误] 不包含市值列")
    
    # 检查页面是否显示空收藏夹或其他问题
    if "watchlist is empty" in content.lower():
        print("[错误] 页面显示收藏夹为空!")
    
    if "no pairs found" in content.lower():
        print("[错误] 页面显示没有找到交易对!")
    
    # 打印文件的开头
    print(f"\n前1000字符预览:")
    print(content[:1000])


def main():
    data_dir = Path("E:/dex_price/data")
    
    for filename in ["yiban.txt", "yiban15.txt"]:
        file_path = data_dir / filename
        if file_path.exists():
            check_html_content(str(file_path))


if __name__ == "__main__":
    main()
