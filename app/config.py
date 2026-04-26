"""
衡策投资系统 - 应用配置
"""
import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    """基础配置"""
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    API_CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv("API_CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]

    # 数据库
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'data' / 'balancealpha.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False

    # 数据目录
    DATA_DIR = BASE_DIR / "data"
    IMPORT_DIR = DATA_DIR / "imports"


class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True
    SQLALCHEMY_ECHO = False  # 设为 True 可查看 SQL 语句


class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG = False

    @property
    def SECRET_KEY(self):
        key = os.getenv("SECRET_KEY")
        if not key:
            raise RuntimeError(
                "生产环境必须通过环境变量 SECRET_KEY 设置密钥，"
                "请运行: python -c \"import secrets; print(secrets.token_hex(32))\" 生成一个"
            )
        return key


# 配置映射
config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
