"""
分布式锁使用示例
"""

import time
import logging
from concurrent.futures import ThreadPoolExecutor

from .redis_lock import RedisLock, with_distributed_lock

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


# 示例1：使用上下文管理器（with语句）
def example_with_context_manager():
    """使用上下文管理器示例"""
    logger.info("示例1：使用上下文管理器")
    
    # 创建一个锁
    with RedisLock("example_lock", expire_seconds=10) as lock:
        if lock.acquired:
            logger.info("成功获取锁，执行受保护的代码...")
            # 模拟一些需要锁保护的操作
            time.sleep(2)
            logger.info("操作完成，锁自动释放")
        else:
            logger.warning("未能获取锁，跳过操作")


# 示例2：使用显式获取和释放锁
def example_explicit_lock():
    """显式获取和释放锁示例"""
    logger.info("示例2：显式获取和释放锁")
    
    lock = RedisLock("example_lock", expire_seconds=10)
    
    # 尝试获取锁
    if lock.acquire():
        try:
            logger.info("成功获取锁，执行受保护的代码...")
            # 模拟一些需要锁保护的操作
            time.sleep(2)
            logger.info("操作完成")
        finally:
            # 确保释放锁
            lock.release()
            logger.info("锁已释放")
    else:
        logger.warning("未能获取锁，跳过操作")


# 示例3：使用装饰器
@with_distributed_lock("decorated_function_lock", expire_seconds=10)
def example_decorated_function():
    """使用装饰器添加分布式锁的函数"""
    logger.info("示例3：使用装饰器")
    logger.info("成功获取锁，执行受保护的代码...")
    # 模拟一些需要锁保护的操作
    time.sleep(2)
    logger.info("操作完成，锁自动释放")


# 示例4：动态锁名称（基于参数）
def dynamic_lock_name(user_id, resource_id):
    """根据参数生成动态锁名称"""
    return f"user_{user_id}_resource_{resource_id}"


@with_distributed_lock(dynamic_lock_name)
def access_user_resource(user_id, resource_id):
    """使用动态锁名称的函数"""
    logger.info(f"示例4：访问用户资源 - 用户ID: {user_id}, 资源ID: {resource_id}")
    # 模拟访问资源
    time.sleep(1)
    logger.info(f"用户 {user_id} 完成对资源 {resource_id} 的访问")


# 示例5：并发环境中的锁竞争
def concurrent_example():
    """并发环境中锁竞争示例"""
    logger.info("示例5：并发环境中的锁竞争")
    
    def worker(worker_id):
        logger.info(f"工作线程 {worker_id} 尝试获取锁")
        with RedisLock("concurrent_lock", expire_seconds=5, retry_times=2) as lock:
            if lock.acquired:
                logger.info(f"工作线程 {worker_id} 成功获取锁")
                # 模拟工作
                time.sleep(2)
                logger.info(f"工作线程 {worker_id} 完成工作")
            else:
                logger.warning(f"工作线程 {worker_id} 未能获取锁")
    
    # 使用线程池模拟并发
    with ThreadPoolExecutor(max_workers=5) as executor:
        for i in range(5):
            executor.submit(worker, i)
    
    # 等待所有线程完成
    time.sleep(1)


# 示例6：锁过期时间的延长
def example_lock_extend():
    """锁过期时间延长示例"""
    logger.info("示例6：锁过期时间延长")
    
    lock = RedisLock("extend_lock", expire_seconds=5)
    
    if lock.acquire():
        try:
            logger.info("成功获取锁，初始过期时间为5秒")
            # 模拟长时间操作前一半
            time.sleep(2)
            
            # 延长锁时间
            if lock.extend(10):
                logger.info("锁过期时间已延长10秒")
            else:
                logger.warning("锁过期时间延长失败")
            
            # 继续操作
            time.sleep(5)
            logger.info("长时间操作完成")
        finally:
            lock.release()
            logger.info("锁已释放")
    else:
        logger.warning("未能获取锁")


if __name__ == "__main__":
    # 运行所有示例
    example_with_context_manager()
    print("\n" + "-" * 50 + "\n")
    
    example_explicit_lock()
    print("\n" + "-" * 50 + "\n")
    
    example_decorated_function()
    print("\n" + "-" * 50 + "\n")
    
    access_user_resource(123, "file_1")
    print("\n" + "-" * 50 + "\n")
    
    concurrent_example()
    print("\n" + "-" * 50 + "\n")
    
    example_lock_extend() 