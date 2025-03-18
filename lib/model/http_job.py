from typing import Dict, Any, Optional, ClassVar, List, Union
from .job import Job, JobStatus

class HttpJob(Job):
    """HTTP请求作业类
    
    表示一个HTTP请求作业，包含请求的所有信息
    """
    
    # 扩展序列化字段映射
    serializable_fields: ClassVar[Dict[str, str]] = {
        **Job.serializable_fields,
        "method": "method",
        "path": "path",
        "headers": "headers",
        "query_params": "query",
        "form_data": "form",
        "json_data": "json",
        "response_status": "response_status",
        "response_headers": "response_headers",
        "response_body": "response_body",
        "error_message": "error"
    }
    
    def __init__(
        self,
        method: str = "GET",
        path: str = "",
        headers: Optional[Dict[str, str]] = None,
        query_params: Optional[Dict[str, Union[str, List[str]]]] = None,
        form_data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Any] = None,
        response_status: Optional[int] = None,
        response_headers: Optional[Dict[str, str]] = None,
        response_body: Optional[Any] = None,
        error_message: Optional[str] = None,
        **kwargs
    ):
        """初始化HTTP请求作业
        
        Args:
            method: HTTP请求方法
            path: 请求路径
            headers: 请求头
            query_params: 查询参数
            form_data: 表单数据
            json_data: JSON数据
            response_status: 响应状态码
            response_headers: 响应头
            response_body: 响应主体
            error_message: 错误信息
            **kwargs: 传递给父类的参数
        """
        super().__init__(**kwargs)
        
        self.method = method.upper()
        self.path = path
        self.headers = headers or {}
        self.query_params = query_params or {}
        self.form_data = form_data
        self.json_data = json_data
        self.response_status = response_status
        self.response_headers = response_headers
        self.response_body = response_body
        self.error_message = error_message
    
    def set_request(
        self,
        method: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        query_params: Optional[Dict[str, Union[str, List[str]]]] = None,
        form_data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Any] = None
    ) -> None:
        """设置请求信息
        
        Args:
            method: HTTP请求方法
            path: 请求路径
            headers: 请求头
            query_params: 查询参数
            form_data: 表单数据
            json_data: JSON数据
        """
        self.method = method.upper()
        self.path = path
        self.headers = headers or {}
        self.query_params = query_params or {}
        self.form_data = form_data
        self.json_data = json_data
        self.update_time = self.create_time
    
    def set_response(
        self,
        status: int,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Any] = None
    ) -> None:
        """设置响应信息
        
        Args:
            status: HTTP状态码
            headers: 响应头
            body: 响应主体
        """
        self.response_status = status
        self.response_headers = headers or {}
        self.response_body = body
        self.error_message = None
        
        if 200 <= status < 300:
            self.update_status(JobStatus.COMPLETED)
        else:
            self.update_status(JobStatus.FAILED)
    
    def set_error(self, error_message: str) -> None:
        """设置错误信息
        
        Args:
            error_message: 错误信息
        """
        self.error_message = error_message
        self.update_status(JobStatus.FAILED) 