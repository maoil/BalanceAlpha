# BalanceAlpha Frontend

独立前端项目，使用 Vite + React + TypeScript，通过 Flask 后端的 `/api/v1` 接口运行。

## 启动

```bash
cd frontend
npm.cmd install
npm.cmd run dev
```

默认前端地址：

```text
http://127.0.0.1:5173
```

后端默认地址：

```text
http://127.0.0.1:5000/api/v1
```

如需切换 API 地址，复制 `.env.example` 为 `.env.local` 并修改：

```env
VITE_API_BASE_URL=http://127.0.0.1:5000/api/v1
```

## 验证

```bash
npm.cmd test
npm.cmd run build
```

当前页面覆盖账户总览、产品、持仓、交易、基金确认、策略信号、参数、回测、日志和市场 VIX 数据。
