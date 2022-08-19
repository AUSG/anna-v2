from .google_spreadsheet_client import GoogleSpreadsheetClient

# [FIXME] 여기의 google_spreadsheet_client 는 뭔가 다른 __init__.py 들과 일맥상통하지 않는다. 왜 이렇게 되었냐면...
#   원래는 `get_instance()`를 노출했는데, 이게 무엇의 instance 인지 코드로 설명하기가 어렵더라.
#   그래서 본의 아니게 해당 파일을 통째로 오픈하게 되었는데 아무리봐도 좋은 그림이 아닌 것 같다. 더 좋은 방법이 없을까.
__all__ = ['google_spreadsheet_client', 'GoogleSpreadsheetClient']

