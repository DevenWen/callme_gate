import unittest
import time
import threading
import sys
import os
from concurrent.futures import ThreadPoolExecutor

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from lib.lock import RedisLock, with_distributed_lock


class TestRedisLockIntegration(unittest.TestCase):
    """集成测试Redis分布式锁与实际Redis服务器的交互
    
    注意：这些测试需要一个运行中的Redis服务器
    """
    
    @classmethod
    def setUpClass(cls):
        """测试前的准备工作"""
        try:
            # 创建一个锁测试连接到Redis
            lock = RedisLock("test_connection")
            lock.acquire()
            lock.release()
            cls.redis_available = True
        except Exception as e:
            print(f"警告: Redis服务不可用，集成测试将被跳过: {e}")
            cls.redis_available = False
    
    def setUp(self):
        """每个测试前的准备，如果Redis不可用则跳过"""
        if not self.redis_available:
            self.skipTest("Redis服务不可用")
    
    def test_simple_lock_usage(self):
        """测试基本的锁获取和释放"""
        lock_name = "integration_test_lock"
        
        # 确保测试开始前锁不存在
        lock = RedisLock(lock_name)
        if lock.redis_client.exists(f"redis_lock:{lock_name}"):
            lock.redis_client.delete(f"redis_lock:{lock_name}")
        
        # 测试锁的获取和释放
        self.assertTrue(lock.acquire(), "应该能够成功获取锁")
        self.assertTrue(lock.redis_client.exists(f"redis_lock:{lock_name}"), "锁键应该存在于Redis中")
        self.assertTrue(lock.release(), "应该能够成功释放锁")
        self.assertFalse(lock.redis_client.exists(f"redis_lock:{lock_name}"), "锁应该已被释放")
    
    def test_lock_expiration(self):
        """测试锁自动过期"""
        lock_name = "expiration_test_lock"
        expiration = 2  # 设置2秒过期
        
        # 确保测试开始前锁不存在
        lock = RedisLock(lock_name)
        if lock.redis_client.exists(f"redis_lock:{lock_name}"):
            lock.redis_client.delete(f"redis_lock:{lock_name}")
        
        # 获取锁并等待过期
        lock = RedisLock(lock_name, expire_seconds=expiration)
        self.assertTrue(lock.acquire(), "应该能够成功获取锁")
        
        # 检查TTL
        ttl = lock.redis_client.ttl(f"redis_lock:{lock_name}")
        self.assertTrue(0 < ttl <= expiration, f"锁应该设置了过期时间，但TTL为{ttl}")
        
        # 等待锁过期
        time.sleep(expiration + 1)
        
        # 验证锁已过期
        self.assertFalse(lock.redis_client.exists(f"redis_lock:{lock_name}"), "锁应该已过期")
    
    def test_lock_extension(self):
        """测试延长锁的过期时间"""
        lock_name = "extension_test_lock"
        initial_expiration = 3
        extension = 3
        
        # 确保测试开始前锁不存在
        lock = RedisLock(lock_name)
        if lock.redis_client.exists(f"redis_lock:{lock_name}"):
            lock.redis_client.delete(f"redis_lock:{lock_name}")
        
        # 获取锁
        lock = RedisLock(lock_name, expire_seconds=initial_expiration)
        self.assertTrue(lock.acquire(), "应该能够成功获取锁")
        
        # 延长锁时间
        time.sleep(1)  # 等待1秒，使TTL减少
        self.assertTrue(lock.extend(extension), "应该能够成功延长锁时间")
        
        # 检查新的TTL
        ttl = lock.redis_client.ttl(f"redis_lock:{lock_name}")
        # 现在TTL应该接近于 (initial_expiration - 1) + extension
        self.assertTrue(extension <= ttl <= initial_expiration + extension, 
                      f"锁的TTL应该已被延长，但TTL为{ttl}")
        
        # 清理
        lock.release()
    
    def test_concurrent_lock_acquisition(self):
        """测试并发情况下的锁竞争"""
        lock_name = "concurrent_test_lock"
        thread_count = 5
        
        # 确保测试开始前锁不存在
        lock = RedisLock(lock_name)
        if lock.redis_client.exists(f"redis_lock:{lock_name}"):
            lock.redis_client.delete(f"redis_lock:{lock_name}")
        
        # 用于记录结果的共享变量
        results = {"success": 0, "failure": 0}
        lock_for_results = threading.Lock()  # 添加线程锁保护共享变量
        
        # 线程函数
        def worker():
            try:
                # 使用不同的实例，确保每个线程有自己的锁ID
                thread_lock = RedisLock(lock_name, retry_times=0)  # 不重试，立即返回结果
                if thread_lock.acquire():
                    try:
                        # 获取锁成功，模拟工作
                        time.sleep(0.5)
                        with lock_for_results:  # 线程安全地更新结果
                            results["success"] += 1
                    finally:
                        thread_lock.release()
                else:
                    with lock_for_results:  # 线程安全地更新结果
                        results["failure"] += 1
            except Exception as e:
                print(f"工作线程异常: {e}")
        
        # 创建线程
        threads = []
        for _ in range(thread_count):
            thread = threading.Thread(target=worker)
            threads.append(thread)
        
        # 启动所有线程
        for thread in threads:
            thread.start()
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
        
        # 验证结果 - 应该只有一个线程成功获取锁
        self.assertEqual(results["success"], 1, f"应该只有一个线程成功获取锁，但有{results['success']}个成功")
        self.assertEqual(results["failure"], thread_count - 1, 
                       f"应该有{thread_count-1}个线程获取锁失败，但有{results['failure']}个失败")
    
    def test_with_statement(self):
        """测试使用with语句的上下文管理器"""
        lock_name = "with_test_lock"
        
        # 确保测试开始前锁不存在
        lock = RedisLock(lock_name)
        key = f"redis_lock:{lock_name}"
        if lock.redis_client.exists(key):
            lock.redis_client.delete(key)
        
        # 使用with语句
        with RedisLock(lock_name, expire_seconds=10) as lock:
            self.assertTrue(lock.acquired, "锁应该被成功获取")
            self.assertTrue(lock.redis_client.exists(key), "锁键应该存在于Redis中")
        
        # with块结束后，锁应该被释放
        self.assertFalse(lock.redis_client.exists(key), "退出with块后锁应该被释放")


class TestRedisLockDecoratorIntegration(unittest.TestCase):
    """集成测试Redis分布式锁装饰器与实际Redis服务器的交互"""
    
    @classmethod
    def setUpClass(cls):
        """测试前的准备工作"""
        try:
            # 创建一个锁测试连接到Redis
            lock = RedisLock("test_connection")
            lock.acquire()
            lock.release()
            cls.redis_available = True
        except Exception as e:
            print(f"警告: Redis服务不可用，集成测试将被跳过: {e}")
            cls.redis_available = False
    
    def setUp(self):
        """每个测试前的准备，如果Redis不可用则跳过"""
        if not self.redis_available:
            self.skipTest("Redis服务不可用")
    
    def test_simple_decorator(self):
        """测试基本的装饰器功能"""
        lock_name = "decorator_integration_test"
        key = f"redis_lock:{lock_name}"
        
        # 确保测试开始前锁不存在
        lock = RedisLock(lock_name)
        if lock.redis_client.exists(key):
            lock.redis_client.delete(key)
        
        # 共享变量用于验证函数被调用
        call_data = {"called": False}
        
        # 定义一个使用装饰器的函数
        @with_distributed_lock(lock_name, expire_seconds=10)
        def decorated_function():
            # 验证锁已被获取
            self.assertTrue(lock.redis_client.exists(key), "函数执行期间锁应该存在")
            call_data["called"] = True
            return "success"
        
        # 调用函数
        result = decorated_function()
        
        # 验证结果
        self.assertEqual(result, "success", "函数应该正常返回")
        self.assertTrue(call_data["called"], "函数应该被调用")
        self.assertFalse(lock.redis_client.exists(key), "函数执行完毕后锁应该被释放")
    
    def test_dynamic_lock_name(self):
        """测试使用动态锁名称的装饰器"""
        # 用于跟踪锁的使用情况
        lock_usage = []
        
        # 创建临时锁以便访问 redis_client
        temp_lock = RedisLock("dummy")
        
        # 包装获取锁和释放锁的过程
        def with_lock(lock_name, func, *args, **kwargs):
            # 确保锁不存在
            key = f"redis_lock:{lock_name}"
            if temp_lock.redis_client.exists(key):
                temp_lock.redis_client.delete(key)
                
            # 创建锁
            lock = RedisLock(lock_name, retry_times=0)
            if lock.acquire():
                try:
                    # 记录使用的锁
                    lock_usage.append(lock_name)
                    # 调用函数
                    result = func(*args, **kwargs)
                    # 验证锁存在
                    self.assertTrue(temp_lock.redis_client.exists(key), 
                                   f"锁 {lock_name} 应该存在")
                    return result
                finally:
                    lock.release()
                    # 验证锁已释放
                    self.assertFalse(temp_lock.redis_client.exists(key), 
                                    f"锁 {lock_name} 应该已释放")
            return None
            
        # 模拟两个不同的资源访问
        result1 = with_lock("resource_100_lock", lambda: "accessed_100")
        result2 = with_lock("resource_200_lock", lambda: "accessed_200")
        
        # 验证结果
        self.assertEqual(result1, "accessed_100", "函数应该正常返回第一个资源的结果")
        self.assertEqual(result2, "accessed_200", "函数应该正常返回第二个资源的结果")
        
        # 验证使用了两个不同的锁
        self.assertEqual(len(lock_usage), 2, "应该使用了两个锁")
        self.assertIn("resource_100_lock", lock_usage, "应该使用了资源100的锁")
        self.assertIn("resource_200_lock", lock_usage, "应该使用了资源200的锁")


if __name__ == "__main__":
    unittest.main() 