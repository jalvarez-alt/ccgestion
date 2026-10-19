import pymysql
import config


def get_db():
    """Abre una conexion nueva a MySQL. Recuerda cerrarla con db.close()."""
    return pymysql.connect(
        host=config.DB_HOST,
        user=config.DB_USER,
        password=config.DB_PASS,
        database=config.DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        init_command="SET time_zone = '-05:00'",   # NOW()/TIMESTAMP en hora de Colombia
    )
