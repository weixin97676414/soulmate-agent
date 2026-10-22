


import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import json
import warnings
warnings.filterwarnings('ignore')


class RiskDashboard:

    
    def __init__(
        self,
        initial_capital: float = 1000000,
        var_confidence: float = 0.95,
        max_position_pct: float = 0.15,
        max_drawdown_pct: float = 0.20
    ):
        self.initial_capital = initial_capital
        self.var_confidence = var_confidence
        self.max_position_pct = max_position_pct
        self.max_drawdown_pct = max_drawdown_pct
        
        self.positions = {}
        self.pnl_history = []
        self.alerts = []
        self.alert_callbacks = []
        
        
        self.limits = {
            'max_position_pct': max_position_pct,
            'max_sector_pct': 0.30,
            'max_leverage': 1.5,
            'max_drawdown': max_drawdown_pct,
            'max_var_pct': 0.05,
        }
        
        
        self.historical_returns = np.random.normal(0.0005, 0.02, 1000)
    
    
    
    def add_position(
        self,
        symbol: str,
        shares: int,
        entry_price: float,
        current_price: float,
        sector: str = 'Other'
    ):

        self.positions[symbol] = {
            'symbol': symbol,
            'shares': shares,
            'entry_price': entry_price,
            'current_price': current_price,
            'sector': sector,
            'market_value': shares * current_price,
            'cost_basis': shares * entry_price,
            'unrealized_pnl': shares * (current_price - entry_price),
            'return_pct': (current_price - entry_price) / entry_price
        }
        
        self._check_limits()
    
    def remove_position(self, symbol: str):

        if symbol in self.positions:
            del self.positions[symbol]
            self._check_limits()
    
    def update_price(self, symbol: str, price: float):

        if symbol in self.positions:
            pos = self.positions[symbol]
            pos['current_price'] = price
            pos['market_value'] = pos['shares'] * price
            pos['unrealized_pnl'] = pos['shares'] * (price - pos['entry_price'])
            pos['return_pct'] = (price - pos['entry_price']) / pos['entry_price']
            
            self._check_limits()
    
    def get_positions(self) -> pd.DataFrame:

        if not self.positions:
            return pd.DataFrame()
        
        df = pd.DataFrame(self.positions.values())
        df = df.set_index('symbol')
        
        
        total_mv = df['market_value'].sum()
        if total_mv > 0:
            df['weight'] = df['market_value'] / total_mv
        
        return df
    
    
    
    def get_risk_metrics(self) -> Dict:

        positions = self.get_positions()
        
        if positions.empty:
            return self._empty_metrics()
        
        
        portfolio_value = self.initial_capital + self._total_unrealized_pnl()
        
        
        total_exposure = positions['market_value'].sum()
        
        
        var_95 = self.calculate_var(0.95)
        var_99 = self.calculate_var(0.99)
        
        
        cvar_95 = self.calculate_cvar(0.95)
        
        
        volatility = self._calculate_volatility()
        
        
        max_dd = self._calculate_max_drawdown()
        
        
        sharpe = self._calculate_sharpe()
        
        
        sortino = self._calculate_sortino()
        
        
        beta = 1.0
        
        
        alpha = self._calculate_alpha()
        
        
        win_rate = (positions['unrealized_pnl'] > 0).mean()
        
        return {
            'portfolio_value': portfolio_value,
            'cash': self.initial_capital - total_exposure,
            'total_exposure': total_exposure,
            'total_pnl': self._total_unrealized_pnl(),
            'return_pct': self._total_unrealized_pnl() / self.initial_capital,
            'var_95': var_95,
            'var_99': var_99,
            'cvar_95': cvar_95,
            'volatility': volatility,
            'max_drawdown': max_dd,
            'sharpe_ratio': sharpe,
            'sortino_ratio': sortino,
            'beta': beta,
            'alpha': alpha,
            'win_rate': win_rate,
            'position_count': len(positions),
            'leverage': total_exposure / portfolio_value if portfolio_value > 0 else 0
        }
    
    def _empty_metrics(self) -> Dict:

        return {
            'portfolio_value': self.initial_capital,
            'cash': self.initial_capital,
            'total_exposure': 0,
            'total_pnl': 0,
            'return_pct': 0,
            'var_95': 0,
            'var_99': 0,
            'cvar_95': 0,
            'volatility': 0,
            'max_drawdown': 0,
            'sharpe_ratio': 0,
            'sortino_ratio': 0,
            'beta': 1.0,
            'alpha': 0,
            'win_rate': 0,
            'position_count': 0,
            'leverage': 0
        }
    
    def calculate_var(self, confidence: float = 0.95) -> float:

        positions = self.get_positions()
        
        if positions.empty:
            return 0
        
        
        portfolio_value = self.initial_capital + self._total_unrealized_pnl()
        
        
        weights = positions['weight'].values
        
        
        volatilities = np.abs(positions['return_pct'].values) * np.sqrt(252)
        
        
        if len(weights) > 1:
            
            corr = np.eye(len(weights)) * 0.3 + 0.7
            cov = np.outer(volatilities, volatilities) * corr
            portfolio_vol = np.sqrt(weights @ cov @ weights)
        else:
            portfolio_vol = volatilities[0] if len(volatilities) > 0 else 0
        
        
        from scipy.stats import norm
        z_score = norm.ppf(1 - confidence)
        
        var = portfolio_value * portfolio_vol * abs(z_score)
        
        return var
    
    def calculate_cvar(self, confidence: float = 0.95) -> float:

        var = self.calculate_var(confidence)
        
        
        from scipy.stats import norm
        z_score = norm.ppf(1 - confidence)
        
        cvar_multiplier = norm.pdf(z_score) / (1 - confidence)
        
        portfolio_value = self.initial_capital + self._total_unrealized_pnl()
        volatility = self._calculate_volatility()
        
        cvar = portfolio_value * volatility * cvar_multiplier
        
        return cvar
    
    def _calculate_volatility(self) -> float:

        positions = self.get_positions()
        
        if positions.empty:
            return 0
        
        
        weights = positions['weight'].values
        volatilities = np.abs(positions['return_pct'].values) * np.sqrt(252)
        
        return np.average(volatilities, weights=weights)
    
    def _calculate_max_drawdown(self) -> float:

        if not self.pnl_history:
            return 0
        
        values = [self.initial_capital] + [h['value'] for h in self.pnl_history]
        
        cummax = np.maximum.accumulate(values)
        drawdown = (np.array(values) - cummax) / cummax
        
        return float(drawdown.min())
    
    def _calculate_sharpe(self) -> float:

        if not self.pnl_history:
            return 0
        
        returns = [h.get('return', 0) for h in self.pnl_history]
        
        if not returns or np.std(returns) == 0:
            return 0
        
        return np.mean(returns) / np.std(returns) * np.sqrt(252)
    
    def _calculate_sortino(self) -> float:

        if not self.pnl_history:
            return 0
        
        returns = [h.get('return', 0) for h in self.pnl_history]
        returns = np.array(returns)
        
        downside = returns[returns < 0]
        
        if len(downside) == 0 or np.std(downside) == 0:
            return 0
        
        return np.mean(returns) / np.std(downside) * np.sqrt(252)
    
    def _calculate_alpha(self) -> float:

        
        positions = self.get_positions()
        
        if positions.empty:
            return 0
        
        portfolio_return = self._total_unrealized_pnl() / self.initial_capital
        benchmark_return = 0.08  
        
        return portfolio_return - benchmark_return
    
    def _total_unrealized_pnl(self) -> float:

        return sum(pos['unrealized_pnl'] for pos in self.positions.values())
    
    
    
    def stress_test(self, scenarios: Dict[str, float]) -> Dict:

        positions = self.get_positions()
        
        if positions.empty:
            return {}
        
        results = {}
        
        for name, shock_pct in scenarios.items():
            
            shocked_pnl = 0
            
            for _, pos in positions.iterrows():
                position_shock = pos['market_value'] * shock_pct
                shocked_pnl += position_shock
            
            results[name] = {
                'pnl': shocked_pnl,
                'return_pct': shocked_pnl / self.initial_capital,
                'var_breach': abs(shocked_pnl) > self.calculate_var(0.95)
            }
        
        return results
    
    
    
    def sector_allocation(self) -> pd.DataFrame:

        positions = self.get_positions()
        
        if positions.empty:
            return pd.DataFrame()
        
        sector_mv = positions.groupby('sector')['market_value'].sum()
        total = sector_mv.sum()
        
        return pd.DataFrame({
            'sector': sector_mv.index,
            'market_value': sector_mv.values,
            'weight': sector_mv.values / total
        })
    
    def factor_exposure(self) -> Dict:

        positions = self.get_positions()
        
        if positions.empty:
            return {}
        
        
        
        return {
            'momentum': np.random.uniform(-0.2, 0.2),
            'value': np.random.uniform(-0.3, 0.3),
            'size': np.random.uniform(-0.1, 0.1),
            'quality': np.random.uniform(0, 0.3),
            'volatility': np.random.uniform(-0.2, 0.2)
        }
    
    
    
    def _check_limits(self):

        metrics = self.get_risk_metrics()
        
        
        if abs(metrics['max_drawdown']) > self.limits['max_drawdown']:
            self.add_alert(
                'critical',
                f"Max drawdown breach: {metrics['max_drawdown']:.1%}"
            )
        
        
        var_pct = metrics['var_95'] / metrics['portfolio_value']
        if var_pct > self.limits['max_var_pct']:
            self.add_alert(
                'warning',
                f"VaR limit breach: {var_pct:.1%}"
            )
        
        
        positions = self.get_positions()
        for symbol, pos in positions.iterrows():
            if pos['weight'] > self.limits['max_position_pct']:
                self.add_alert(
                    'warning',
                    f"Position limit breach: {symbol} {pos['weight']:.1%}"
                )
        
        
        if metrics['leverage'] > self.limits['max_leverage']:
            self.add_alert(
                'critical',
                f"Leverage limit breach: {metrics['leverage']:.2f}x"
            )
    
    def add_alert(self, level: str, message: str):

        alert = {
            'timestamp': datetime.now().isoformat(),
            'level': level,  
            'message': message
        }
        
        self.alerts.append(alert)
        
        
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except:
                pass
    
    def get_alerts(self, level: str = None) -> List[Dict]:

        if level:
            return [a for a in self.alerts if a['level'] == level]
        return self.alerts
    
    def clear_alerts(self):

        self.alerts = []
    
    def set_alert_callback(self, callback):

        self.alert_callbacks.append(callback)
    
    
    
    def generate_report(self, format: str = 'dict') -> Dict:

        metrics = self.get_risk_metrics()
        positions = self.get_positions()
        sectors = self.sector_allocation()
        factors = self.factor_exposure()
        
        report = {
            'generated_at': datetime.now().isoformat(),
            'summary': metrics,
            'positions': positions.to_dict() if not positions.empty else {},
            'sectors': sectors.to_dict() if not sectors.empty else {},
            'factors': factors,
            'alerts': self.alerts[-10:]  
        }
        
        if format == 'json':
            return json.dumps(report, indent=2, default=str)
        
        return report
    
    def get_daily_summary(self) -> str:

        metrics = self.get_risk_metrics()
        
        summary = f"""
Risk Daily Summary
==================
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Portfolio Value: ¥{metrics['portfolio_value']:,.0f}
Total P&L: ¥{metrics['total_pnl']:,.0f} ({metrics['return_pct']:.2%})
Positions: {metrics['position_count']}

Risk Metrics
-----------
VaR (95%): ¥{metrics['var_95']:,.0f}
CVaR (95%): ¥{metrics['cvar_95']:,.0f}
Volatility: {metrics['volatility']:.2%}
Max Drawdown: {metrics['max_drawdown']:.2%}
Sharpe Ratio: {metrics['sharpe_ratio']:.2f}
Beta: {metrics['beta']:.2f}

Alerts: {len(self.alerts)}
"""
        
        return summary
    
    
    
    def start_dashboard(self, port: int = 8050):

        print(f"Starting risk dashboard on port {port}...")
        print("In production, would use Dash or Streamlit for visualization")
        
        
        
        
        
        
    
    def plot_pnl_history(self):

        
        pass
    
    def plot_scenarios(self):

        pass


def main():

    print("Quant Risk Dashboard")
    print("=" * 50)
    
    
    dashboard = RiskDashboard(initial_capital=1000000)
    
    
    dashboard.add_position('600519', 1000, 1800.0, 1850.0, 'Consumer')
    dashboard.add_position('000858', 5000, 45.0, 48.0, 'Consumer')
    dashboard.add_position('600036', 10000, 35.0, 34.0, 'Finance')
    
    
    metrics = dashboard.get_risk_metrics()
    
    print(f"Portfolio Value: ¥{metrics['portfolio_value']:,.0f}")
    print(f"VaR (95%): ¥{metrics['var_95']:,.0f}")
    print(f"Sharpe: {metrics['sharpe_ratio']:.2f}")
    print(f"Max Drawdown: {metrics['max_drawdown']:.2%}")
    
    
    scenarios = {
        'Market Crash -20%': -0.20,
        'Covid -30%': -0.30,
        'Rate Hike -10%': -0.10
    }
    
    results = dashboard.stress_test(scenarios)
    print("\nStress Test:")
    for name, result in results.items():
        print(f"  {name}: ¥{result['pnl']:,.0f}")


if __name__ == "__main__":
    main()
