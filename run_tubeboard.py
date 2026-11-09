"""실행 파일(PyInstaller)의 진입점. 소스로 쓸 때는 `python3 -m tubeboard` 를 쓴다."""
from tubeboard.server import main

raise SystemExit(main())
