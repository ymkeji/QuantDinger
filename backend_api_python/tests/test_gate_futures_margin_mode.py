from unittest.mock import patch

from app.services.live_trading.base import LiveOrderResult
from app.services.live_trading.gate import GateUsdtFuturesClient
from app.services.pending_orders import live_order_phases


def _gate_client() -> GateUsdtFuturesClient:
    client = GateUsdtFuturesClient(api_key="k", secret_key="s")
    client.get_contract = lambda **_kwargs: {"leverage_max": "100"}
    client.get_position_mode = lambda: "single"
    return client


def test_gate_futures_cross_margin_uses_cross_leverage_limit():
    client = _gate_client()

    with patch.object(
        client, "_signed_request", return_value={"cross_leverage_limit": "5"}
    ) as mock_req:
        assert client.set_leverage(contract="BTC_USDT", leverage=5, margin_mode="cross")

    assert mock_req.call_args.kwargs["params"] == {
        "leverage": "0",
        "cross_leverage_limit": "5",
    }


def test_gate_futures_isolated_margin_uses_position_leverage():
    client = _gate_client()

    with patch.object(client, "_signed_request", return_value={"leverage": "5"}) as mock_req:
        assert client.set_leverage(contract="BTC_USDT", leverage=5, margin_mode="isolated")

    assert mock_req.call_args.kwargs["params"] == {"leverage": "5"}


def test_gate_strategy_order_passes_payload_margin_mode(monkeypatch):
    class FakeGateFutures:
        def set_leverage(self, **kwargs):
            self.leverage_kwargs = kwargs
            return True

        def place_market_order(self, **kwargs):
            return LiveOrderResult(
                exchange_id="gate",
                exchange_order_id="1",
                filled=0,
                avg_price=0,
                raw=kwargs,
            )

    monkeypatch.setattr(live_order_phases, "GateUsdtFuturesClient", FakeGateFutures)
    client = FakeGateFutures()

    live_order_phases.place_live_market_order(
        client=client,
        symbol="BTC/USDT",
        side="buy",
        amount=0.01,
        reduce_only=False,
        pos_side="long",
        client_order_id="oid",
        market_type="swap",
        payload={"margin_mode": "cross"},
        exchange_config={"margin_mode": "isolated"},
        leverage=5,
        ref_price=70000,
        spot_quote_amt=0,
        spot_market_buy_uses_quote=False,
    )

    assert client.leverage_kwargs == {
        "contract": "BTC_USDT",
        "leverage": 5,
        "margin_mode": "cross",
    }
