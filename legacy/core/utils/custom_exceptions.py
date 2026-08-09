
class CustomException(Exception):
    """Base exception class for orchestrator-specific errors"""
    def __init__(self, message, original_error=None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)

class PlannerError(CustomException):
    """Raised when planner execution fails"""
    pass

class BrowserNavigationError(CustomException):
    """Raised when browser navigation fails"""
    pass

class SSAnalysisError(CustomException):
    """Raised when SS analysis fails"""
    pass

class CritiqueError(CustomException):
    """Raised when critique agent fails"""
    pass



class InvalidURLError(ValueError):
    """Exception raised when URL validation fails.
    
    Attributes:
        message -- explanation of the error
        url -- the invalid URL that caused the error (optional)
        error_code -- numeric error code (optional)
    """
    
    def __init__(
        self, 
        message: str, 
        url: str = None, 
        error_code: int = None
    ) -> None:
        self.url = url
        self.error_code = error_code
        super().__init__(message)
        
    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.url:
            base_msg = f"{base_msg} (URL: {self.url})"
        if self.error_code:
            base_msg = f"{base_msg} [Error Code: {self.error_code}]"
        return base_msg



class ToolSequenceError(Exception):
    """Exception raised when tool call/response sequence validation fails.
    
    Attributes:
        message -- explanation of the error
        message_index -- index where the sequence error occurred
        message_content -- content of the problematic message
        missing_ids -- list of tool call IDs missing responses
        last_events -- recent sequence history for debugging
    """
    
    def __init__(
        self, 
        message: str,
        message_index: int = None,
        message_content: str = None,
        missing_ids: list = None,
        last_events: list = None
    ) -> None:
        self.message_index = message_index
        self.message_content = message_content
        self.missing_ids = missing_ids or []
        self.last_events = last_events or []
        super().__init__(message)
    
    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.message_index is not None:
            parts.append(f"Message Index: {self.message_index}")
        if self.message_content:
            parts.append(f"Content: {self.message_content[:100]}...")
        if self.missing_ids:
            parts.append(f"Missing IDs: {', '.join(self.missing_ids[:5])}")
        if self.last_events:
            parts.append(f"Recent Events: {' → '.join(self.last_events[-5:])}")
        return " | ".join(parts)
