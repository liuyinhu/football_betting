<script>
export default {
  onLaunch() {
    // 小程序启动
  },
  onShow() {},
  onHide() {},
}
</script>

<style>
/* 全局深色主题（迁移自网页版 style.css，px → rpx / 保留颜色变量语义） */
page {
  --bg: #0f1420;
  --card: #1a2131;
  --card2: #212a3d;
  --line: #2c374d;
  --text: #e6ebf5;
  --muted: #8b96ab;
  --home: #4f8cff;
  --draw: #b7b7b7;
  --away: #ff7a59;
  --green: #2ecc71;
  --gold: #f5c451;

  background-color: #0f1420;
  color: #e6ebf5;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  line-height: 1.5;
}

/* 通用状态行 */
.status-line {
  text-align: center;
  color: var(--muted);
  padding: 60rpx 0;
  font-size: 26rpx;
}
.status-line.error {
  color: var(--away);
}
</style>
