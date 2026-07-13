import math
from scipy.stats import norm

# Standard Black-Scholes for European Options
def black_scholes_price(S, K, T, r, sigma, option_type="call"):
    """
    S: Spot Price
    K: Strike Price
    T: Time to Expiration (in years)
    r: Risk-free rate (e.g. 0.0)
    sigma: Implied Volatility
    """
    if T <= 0:
        return max(0.0, S - K) if option_type == "call" else max(0.0, K - S)
        
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    
    if option_type == "call":
        price = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    else:
        price = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        
    return max(0.0, price)

def black_scholes_delta(S, K, T, r, sigma, option_type="call"):
    if T <= 0:
        if option_type == "call":
            return 1.0 if S > K else 0.0
        else:
            return -1.0 if S < K else 0.0
            
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    if option_type == "call":
        return norm.cdf(d1)
    else:
        return norm.cdf(d1) - 1.0

def find_strike_by_delta(S, target_delta, T, r, sigma, option_type="call"):
    """
    Reverse engineers the strike price for a given target delta.
    """
    # d1 = norm.ppf(target_delta) for calls
    # d1 = norm.ppf(target_delta + 1) for puts
    try:
        if option_type == "call":
            d1 = norm.ppf(target_delta)
        else:
            d1 = norm.ppf(target_delta + 1.0)
            
        # d1 = (ln(S/K) + (r + sigma^2/2)T) / (sigma*sqrt(T))
        # d1 * sigma * sqrt(T) - (r + sigma^2/2)T = ln(S/K)
        # K = S / exp(d1 * sigma * sqrt(T) - (r + sigma^2/2)T)
        
        exponent = d1 * sigma * math.sqrt(T) - (r + 0.5 * sigma ** 2) * T
        K = S / math.exp(exponent)
        
        # Round to nearest 100 for typical BTC strikes
        return round(K / 100) * 100
    except:
        return S # Fallback
