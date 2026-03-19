# DEX Price Monitor - 新电脑部署指南

本指南将帮助你在新电脑上部署和运行 DEX 价格监控系统。

## 1. 环境准备 (Prerequisites)

在新电脑上，你需要安装以下软件：

### 1.1 Python 环境
- 推荐版本：Python 3.10 或更高版本
- 确保在安装时勾选 "Add Python to PATH"

### 1.2 Node.js 环境 (前端)
- 推荐版本：Node.js 18 (LTS) 或更高版本
- 下载地址：[https://nodejs.org/](https://nodejs.org/)

### 1.3 浏览器
- 推荐安装 **Google Chrome** 或 **Microsoft Edge**
- 系统会自动调用已安装的浏览器进行数据采集

### 1.4 Git (可选)
- 用于版本控制，推荐安装：[https://git-scm.com/](https://git-scm.com/)

---

## 2. 安装步骤

假设你已经将项目文件复制到了新电脑的 `E:\project_claude_0103` 目录（或其他位置，以下以该路径为例）。

### 2.1 后端配置 (Python)

1. **打开终端 (PowerShell 或 CMD)**
   进入项目根目录：
   ```powershell
   cd E:\project_claude_0103
   ```

2. **创建虚拟环境 (推荐)**
   创建一个独立的 Python 环境，避免污染系统环境：
   ```powershell
   python -m venv .venv
   ```

3. **激活虚拟环境**
   ```powershell
   .\.venv\Scripts\activate
   ```
   *(激活后，命令行前面会出现 `(.venv)` 字样)*

4. **安装依赖**
   使用我在根目录生成的 `requirements.txt` 安装所有必要的库：
   ```powershell
   pip install -r requirements.txt
   ```
   *注意：如果下载速度慢，可以使用国内镜像：*
   ```powershell
   pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
   ```

5. **初始化数据库**
   进入代码目录并运行初始化脚本：
   ```powershell
   cd dex_price
   python init_db_tables.py
   ```
   这将在 `dex_price/data/` 目录下创建 `dex_monitor.db` 数据库文件。

### 2.2 前端配置 (Node.js)

1. **进入前端目录**
   ```powershell
   cd web
   ```

2. **安装依赖**
   ```powershell
   npm install
   ```

---

## 3. 运行项目

项目根目录下的 `dex_price` 文件夹中有一个启动脚本：`start_dashboard.bat`。

### 3.1 启动方式
1. 打开文件夹 `E:\project_claude_0103\dex_price`
2. 双击运行 **`start_dashboard.bat`**

该脚本会自动：
1. 启动 Python 后端 API (端口 8000)
2. 启动前端页面 (端口 5173)
3. 自动打开浏览器访问看板页面

### 3.2 常见问题

- **DrissionPage 浏览器报错**：
  如果启动时提示找不到浏览器，请确保 Chrome 或 Edge 安装在默认路径。
  可以通过修改 `config/app_settings.json` (如有) 或环境变量来指定浏览器路径。

- **依赖缺失**：
  如果提示 `ModuleNotFoundError`，请确保你已经激活了虚拟环境并运行了 `pip install` 步骤。

- **端口占用**：
  如果提示端口 8000 或 5173 被占用，请关闭相关进程或修改启动配置。

---
**部署完成！开启你的监控之旅吧。**

---

## 4. 局域网访问 (LAN Access)

如果你有另一台电脑（或手机）在同一局域网内，可以远程访问看板。

### 4.1 获取主机 IP 地址
在运行 DEX 监控的电脑 (电脑A) 上，打开 PowerShell 或 CMD，输入：
```powershell
ipconfig
```
找到 **IPv4 地址**，例如 `192.168.1.5`。

### 4.2 从其他设备访问
在另一台设备上打开浏览器，输入：
```
http://192.168.1.5:5173
```
将 `192.168.1.5` 替换为你电脑A的实际 IP 地址。

### 4.3 注意事项
- 确保电脑A的 **Windows 防火墙** 允许 5173 (前端) 和 8000 (API) 端口通过。
- 如果无法访问，尝试暂时关闭防火墙进行测试。

