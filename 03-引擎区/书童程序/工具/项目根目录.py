"""统一的项目根目录查找工具

项目根目录的判定标准：存在 "01-配置区" 目录。
所有需要计算绝对路径的模块/脚本，都应通过这里获取根目录，
避免硬编码个人路径或重复实现查找逻辑。
"""

from pathlib import Path


ROOT_MARKER = "01-配置区"


def get_project_root() -> Path:
    """从当前文件向上查找，返回包含 01-配置区 的项目根目录"""
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / ROOT_MARKER).exists():
            return parent
    raise FileNotFoundError(f"找不到项目根目录（缺少 {ROOT_MARKER} 标记）")
