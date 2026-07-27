# DataExport Studio（数导工坊）

一个只读 Windows 桌面工具：连接数据库、从元数据中选择表、按一个可选字段条件筛选，并导出为带格式的 Excel 工作簿。

## 当前能力

- 支持 SQLite、MySQL/MariaDB、PostgreSQL、SQL Server、MongoDB 的连接配置。
- 表名与字段名只能从已连接数据库的元数据中选择；筛选值由 SQLAlchemy 参数化绑定。
- 支持 `>`、`<`、`=`、`>=`、`<=`、包含、不包含七种筛选运算，可动态添加多个条件并选择 `AND` 或 `OR` 连接关系。
- 可按所选字段升序或降序导出。
- 使用流式读取和 `openpyxl` 写入，默认最多导出 1,000,000 行；超过单工作表限制时自动新建工作表。
- Excel 对齐 CertFlow 审计日志格式：宋体、白底、仅表头加粗、轻量细网格和居中显示；列宽按前 200 行数据样本计算。
- 导出进度默认显示 `0%`；导出期间平滑更新，完成时显示 `100%`。

Oracle、任意 SQL、写操作与凭据持久化不属于当前范围。

## 环境与启动

需要 Python 3.9 或更高版本。建议使用虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,build]"
dataexport-studio
```

SQL Server 使用默认安装的 `pymssql`，通过 TDS 协议直接连接，不需要安装 Microsoft ODBC Driver 或 SQL Server Native Client。

MongoDB 使用 `pymongo 3.13` 直接连接，不需要安装 MongoDB 客户端，兼容 MongoDB 4.0 等旧服务。可使用无认证连接；若目标服务启用了认证，用户名和密码必须同时填写。

## 使用流程

1. 选择数据库类型并填写连接信息。SQLite 的“SQLite 文件”填写 `.db` 文件路径；其他关系型数据库无需预先填写数据库。PostgreSQL 和 SQL Server 分别以 `postgres`、`master` 作为初始连接库。MongoDB 默认端口为 `27017`，用户名和密码可以同时留空。
2. 点击“测试并连接”，从“数据库”和数据表下拉框选择导出对象。关系型数据库中“数据库”显示可访问的 schema；MongoDB 中“数据库”显示 MongoDB Database，“数据表”显示 Collection。
3. 可选地填写一个或多个筛选条件，选择 `AND` 或 `OR` 连接关系；输入 `NULL` 可匹配空值。勾选“按字段排序”后可选择排序字段与方向。
4. 选择导出目录，确认或修改默认的文件名（`{数据库}-{数据表}-{YYYYMMDD}.xlsx`），确认最大行数后开始导出。

下拉框仅支持点击选择，滚轮会继续滚动页面而不会意外切换配置。窗口激活时按回车可执行“测试并连接”；Windows 启动时会将前台窗口输入法切换为英文模式。

连接账户应授予最小的只读权限。应用不会记录密码、完整连接串、筛选值或查询结果。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest
```

测试使用 SQLite 内存数据库和 `mongomock`，不要求外部数据库服务。

## Windows 打包

### 自定义图标（可选）

公开仓库不包含品牌图标。需要本地图标时，将 Windows `.ico` 文件放到 `assets/icons/app.ico`；该文件已被 Git 忽略，不会提交到远程仓库。构建脚本检测到文件后，会将图标嵌入 EXE，并设置为窗口和任务栏图标。

未提供图标时，构建仍会正常完成，只使用默认应用图标。图标仅在构建时使用，发布后的 EXE 不依赖项目目录中的 `.ico` 文件。

默认构建目录包，生成的可执行文件为 `dist/数据库导出工具/数据库导出工具.exe`：

```powershell
.\scripts\build.ps1
```

需要单个可执行文件时使用：

```powershell
.\scripts\build.ps1 -OneFile
```

单文件构建会生成 `dist/数据库导出工具.exe`，首次启动会比目录包稍慢。
