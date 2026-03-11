from __future__ import annotations
import io
import logging

log = logging.getLogger(__name__)


class SignalChart:
    def generate(self, signal, candles: list) -> bytes | None:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import matplotlib.gridspec as gridspec
            from matplotlib.dates import DateFormatter
            from src.market.indicators import Indicators

            if not candles or len(candles) < 5:
                return None

            ind = Indicators()
            closes = [c.close for c in candles]
            times = [c.timestamp for c in candles]

            # RSI
            rsi_values = []
            for i in range(len(closes)):
                r = ind.rsi(closes[:i+1], 14) if i >= 14 else None
                rsi_values.append(r)

            # SMA
            sma_val = ind.sma(closes, 200) if len(closes) >= 200 else None

            fig = plt.figure(figsize=(8, 5), facecolor="#1a1a2e")
            gs = gridspec.GridSpec(2, 1, height_ratios=[4, 1], hspace=0.05)

            ax_price = fig.add_subplot(gs[0])
            ax_rsi = fig.add_subplot(gs[1], sharex=ax_price)

            for ax in [ax_price, ax_rsi]:
                ax.set_facecolor("#1a1a2e")
                ax.tick_params(colors="gray", labelsize=8)
                for spine in ax.spines.values():
                    spine.set_edgecolor("#333355")

            # Price line
            coin = signal.symbol.replace("USDT", "")
            colors = {
                "BTC": "#f7931a", "ETH": "#627eea", "SOL": "#9945ff",
                "BNB": "#f3ba2f", "XRP": "#346aa9",
            }
            line_color = colors.get(coin, "#00d4ff")
            ax_price.plot(times, closes, color=line_color, linewidth=1.5, label=coin)

            # SMA
            if sma_val:
                price_min = min(closes[-min(50, len(closes)):])
                price_max = max(closes[-min(50, len(closes)):])
                if price_min * 0.95 <= sma_val <= price_max * 1.05:
                    ax_price.axhline(sma_val, color="#ff8c00", linewidth=0.8,
                                     linestyle="--", alpha=0.8, label=f"SMA200 ${sma_val:,.0f}")

            # Signal marker
            signal_color = "#00ff88" if signal.type.is_bullish() else "#ff4444"
            marker = "^" if signal.type.is_bullish() else "v"
            ax_price.plot(times[-1], closes[-1], marker=marker, color=signal_color,
                          markersize=12, zorder=5)

            ax_price.set_ylabel("Цена", color="gray", fontsize=9)
            ax_price.legend(loc="upper left", facecolor="#1a1a2e", edgecolor="#333355",
                            labelcolor="white", fontsize=8)
            ax_price.yaxis.set_major_formatter(
                plt.FuncFormatter(lambda x, _: f"${x:,.0f}" if x >= 100 else f"${x:.4f}")
            )

            # RSI subplot
            valid_rsi = [(t, r) for t, r in zip(times, rsi_values) if r is not None]
            if valid_rsi:
                rsi_times, rsi_vals = zip(*valid_rsi)
                ax_rsi.plot(rsi_times, rsi_vals, color="#aa88ff", linewidth=1)
                ax_rsi.axhline(70, color="#ff4444", linewidth=0.5, linestyle="--", alpha=0.7)
                ax_rsi.axhline(30, color="#00ff88", linewidth=0.5, linestyle="--", alpha=0.7)
                ax_rsi.set_ylim(0, 100)
                ax_rsi.set_ylabel("RSI", color="gray", fontsize=8)
                ax_rsi.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0f}"))

            ax_rsi.xaxis.set_major_formatter(DateFormatter("%m/%d"))
            plt.setp(ax_price.get_xticklabels(), visible=False)

            buf = io.BytesIO()
            plt.savefig(buf, format="png", dpi=100, bbox_inches="tight",
                        facecolor="#1a1a2e")
            plt.close(fig)
            buf.seek(0)
            return buf.read()
        except Exception as e:
            log.warning("Chart generation failed: %s", e)
            return None
