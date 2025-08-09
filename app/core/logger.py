import sys
from pathlib import Path
from loguru import logger
from app.core.config import settings

LOG_FORMAT = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"

LOG_FORMAT_WITH_CONTEXT = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level> | {extra}"

def setup_logging(
    log_level: str = "INFO",
    enable_file_logging: bool = True,
    log_dir: str = "logs",
    rotation: str = "10 MB",
    retention: str = "7 days",
    compression: str = "zip",
    serialize: bool = False
):
    logger.remove()
    
    logger.add(
        sys.stderr,
        format=LOG_FORMAT,
        level=log_level,
        colorize=True,
        backtrace=True,
        diagnose=False
    )
    
    if enable_file_logging:
        log_path = Path(log_dir)
        log_path.mkdir(exist_ok=True)
        
        logger.add(
            log_path / "n0ir_api.log",
            format=LOG_FORMAT,
            level=log_level,
            rotation=rotation,
            retention=retention,
            compression=compression,
            backtrace=True,
            diagnose=False,
            serialize=False
        )
        
        logger.add(
            log_path / "n0ir_api_error.log",
            format=LOG_FORMAT,
            level="ERROR",
            rotation=rotation,
            retention=retention,
            compression=compression,
            backtrace=True,
            diagnose=True,
            serialize=False
        )
        
        if serialize:
            logger.add(
                log_path / "n0ir_api.json",
                format="{message}",
                level=log_level,
                rotation=rotation,
                retention=retention,
                compression=compression,
                serialize=True
            )

def get_logger(name: str = None):
    if name:
        return logger.bind(context=name)
    return logger

setup_logging(
    log_level=getattr(settings, 'LOG_LEVEL', 'INFO'),
    enable_file_logging=getattr(settings, 'ENABLE_FILE_LOGGING', True),
    log_dir=getattr(settings, 'LOG_DIR', 'logs')
)

__all__ = ['logger', 'get_logger', 'setup_logging']