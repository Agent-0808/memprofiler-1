"""
Copyright (c) 2026, Chen Jie, Joungtao, Xuzheng Jiang
All rights reserved.
This source code is licensed under the BSD-2-Clause license found in the
LICENSE file in the root directory of this source tree.
"""

# utils.py
import logging

def setup_logging():
    """配置全局日志记录器"""
    # 创建根日志记录器
    root_logger = logging.getLogger()
    # 避免重复添加处理器
    if root_logger.hasHandlers():
        return
        
    root_logger.setLevel(logging.INFO)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 定义日志格式
    formatter = logging.Formatter(
        '[%(asctime)s]-%(levelname)s- %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    
    root_logger.addHandler(console_handler)