"""
衡策投资系统 - Flask 扩展实例

所有扩展在此处实例化，在 app factory 中初始化
"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
