import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import scipy.optimize as sco
import pandas_datareader as pdr
import datetime as dt
import dash
from dash import dcc
from dash import html
import talib as ta
import plotly.express as px
from dash import Dash, dcc, html
from dash.dependencies import Input, Output, State
import time
import copy
import yfinance as yf

def getData(tickers):
    start = dt.datetime(2016, 1, 1)
    end = dt.datetime(2022, 8, 1)

    try:
        # Download the data
        data = yf.download(tickers, start=start, end=end)
    except Exception as e:
        print(f"Error fetching data: {e}")
        data = None

    if data is not None:
        print("Data columns:", data.columns)  # Print the column names to check for 'Close'

        # Extract the 'Close' prices for each ticker (using MultiIndex)
        data = data['Close']

        # Calculate exponential moving averages (EMA)
        exp1 = data.ewm(span=12, adjust=False).mean()
        exp2 = data.ewm(span=26, adjust=False).mean()
        MACD = exp1 - exp2
        signal_line = MACD.ewm(span=9, adjust=False).mean()

        # Calculate moving averages (50-day and 200-day)
        fifty = data.rolling(window=50).mean()
        twohundred = data.rolling(window=200).mean()

        return data, fifty, twohundred, MACD, signal_line
    else:
        return None, None, None, None, None

def setup(startyear, endyear, month, tickers, data):
    """
    Description: For the time range provided, calculated a dataframe of log Returns
    Output: log_returns
    """
    start = data.index.searchsorted(dt.datetime(startyear, month, 1))
    end = data.index.searchsorted(dt.datetime(endyear, month, 1))
    data = data.iloc[start:end]#finds data for the time range provided
    log_returns = np.log(data/data.shift())
    return log_returns

def portfolio_annualised_performance(weights, mean_returns, cov_matrix):
    returns = np.sum(mean_returns*weights ) *252
    std = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights))) * np.sqrt(252)
    return std, returns

def random_portfolios(num_portfolios, mean_returns, cov_matrix, risk_free_rate, log_returns, stock_num):
    results = np.zeros((3,num_portfolios))
    weights_record = []
    for i in range(num_portfolios):
        weights = np.random.random(stock_num)
        weights /= np.sum(weights)
        weights_record.append(weights)
        portfolio_std_dev, portfolio_return = portfolio_annualised_performance(weights, mean_returns, cov_matrix)
        results[0,i] = portfolio_std_dev
        results[1,i] = portfolio_return
        results[2,i] = (portfolio_return - risk_free_rate) / portfolio_std_dev
    return results, weights_record

def display_simulated_ef_with_random(mean_returns, cov_matrix, num_portfolios, risk_free_rate, log_returns, stock_num):
    """
    Description: prints the Maximum Sharpe Ratio Portfolio Allocation, annualised return, and annualised volatility.
    Input: mean_returns, cov_matrix, num_portfolios, risk_free_rate, log_returns
    Output: A list of percentages of how much to invest in each stock
    """
    results, weights = random_portfolios(num_portfolios,mean_returns, cov_matrix, risk_free_rate, log_returns, stock_num)
    max_sharpe_idx = np.argmax(results[2])
    sdp, rp = results[0,max_sharpe_idx], results[1,max_sharpe_idx]
    max_sharpe_allocation = pd.DataFrame(weights[max_sharpe_idx],index=log_returns.columns,columns=['allocation'])
    money = []
    max_sharpe_allocation.allocation = [round(i*100,2)for i in max_sharpe_allocation.allocation]
    for i in max_sharpe_allocation.allocation:
        amount = round((i/100.0),4)#adds each percentage to the list, rounds to 4 decimal places
        money.append(amount)
    max_sharpe_allocation = max_sharpe_allocation.T
    return money

def returns_calculation(percentages, initial_investment, curr_year, curr_end_year, curr_month, curr_end_month, data):
    """
    Description: Invests initial_investment in 4 stocks based on a percentage
    calculates the change in what was invested after each day
    output: Change in the investment after each month
    """
    start = data.index.searchsorted(dt.datetime(curr_year, curr_month, 1))
    start = start - 1
    end = data.index.searchsorted(dt.datetime(curr_end_year, curr_end_month, 1))
    new_data = data.iloc[start:end]#finds data for the time range provided
    market_value = np.sum((new_data/new_data.iloc[0])*percentages*initial_investment, axis=1)
    print("Return after", curr_year, "/", curr_month, ":", market_value[-1])
    return market_value[-1]

def accounting_for_movavg(percentages, fifty, twohundred, curr_year,curr_end_year, curr_month, curr_end_month):
    """
    Description: Calculates percentages accounting for the fifty and two hundred MAs
    Output: New normalized percentage list
    """
    fiftystart = fifty.index.searchsorted(dt.datetime(curr_year, curr_month, 1))#gets the data row number for fifty day moving average
    twohundredstart = twohundred.index.searchsorted(dt.datetime(curr_year, curr_month, 1))
    new_fifty = fifty.iloc[fiftystart]#accesses row for fifty day moving average
    new_twohundred = twohundred.iloc[twohundredstart]
    flag = (new_fifty - new_twohundred)/new_twohundred#checks to see if the moving averages differ by a distinct margin
    counter = 0
    percentages_copy = copy.deepcopy(percentages)
    for i in flag:
        if i < -0.01:
            percentages_copy[counter] = percentages[counter]*0.5
        elif i > 0.01:
            percentages_copy[counter] = percentages[counter]*1.5
        counter += 1
    norm = [round(float(i)/sum(percentages_copy), 4) for i in percentages_copy]#normalizes the list so they add to 1
    return norm

def macd_signal(MACD, signal_line, curr_year, curr_month, percentages):
    macd_val = MACD.index.searchsorted(dt.datetime(curr_year, curr_month, 1))
    signal_val = signal_line.index.searchsorted(dt.datetime(curr_year, curr_month, 1))
    new_macd = MACD.iloc[macd_val]
    new_signal = signal_line.iloc[signal_val]
    percentages_copy = copy.deepcopy(percentages)
    for i in range(len(percentages)):
        if (new_macd[i] > new_signal[i]):
            percentages_copy[i] = percentages[i]*0.9
        elif (new_macd[i] < new_signal[i]):
            percentages_copy[i] = percentages[i]*1.1
    for i in range(len(percentages)):
        if (new_macd[i] > 0 and new_signal[i] > 0):
            percentages_copy[i] = percentages[i]*1.5
    norm = [round(float(i)/sum(percentages_copy), 4) for i in percentages_copy]#normalizes the list so they add to 1
    return norm

def sigmoidal_function(sigmoidal_values, percentages):
    """
    Description: uses the function- L/(1 + e^(-k(x - xo)))
    where L is the curve's maximum value
    xo is the x-value of the sigmoid's midpoint
    k is the logistic growth rate(Steepness) of the curve
    Output: new normalized percentage list
    """
    percentages_copy = copy.deepcopy(percentages)
    for i in range(len(sigmoidal_values)):
        weightage = 2/(1 + e**(-1*sigmoidal_values[i]))
        percentages[i]*weightage
    norm = [round(float(i)/sum(percentages_copy), 4) for i in percentages_copy]#normalizes the list so they add to 1
    return norm

def calculations(tickers, curr_year, initial_investment):
    data, fifty, twohundred, MACD, signal_line = getData(tickers)
    sigmoidal_values = []
    for i in range(len(tickers)):
        sigmoidal_values.append(0)
    num_portfolios = 25000
    risk_free_rate = 0.0178
    count = 0
    curr_end_year = curr_year
    past_start = curr_year - 2
    past_end = curr_year
    month = 1
    counter = 1
    curr_month = 1
    curr_end_month = 2
    market_value = []
    market_value.append(initial_investment)
    x_values = []
    x_values.append(counter)
    log_returns = setup(past_start, past_end, month, tickers, data)
    static_y = []
    static_investment = initial_investment
    static_movavg = initial_investment
    dynamic_movavg = initial_investment
    static_macd_signal_investment = initial_investment
    dynamic_macd_signal_investment = initial_investment
    macd_signal_investment = initial_investment
    static_y.append(static_investment)
    static_ma = []
    dynamic_ma = []
    static_macd_signal = []
    dynamic_macd_signal = []
    normal_macd_signal = []
    static_ma.append(static_movavg)
    dynamic_ma.append(dynamic_movavg)
    static_macd_signal = [initial_investment]
    dynamic_macd_signal = [initial_investment]
    normal_macd_signal = [initial_investment]
    stock_num = len(tickers)

    while not(curr_year == 2022 and curr_month == 8):
        log_returns = setup(past_start, past_end, month, tickers, data)
        cov_matrix = log_returns.cov()
        mean_returns = log_returns.mean()
        percentages = display_simulated_ef_with_random(mean_returns, cov_matrix, num_portfolios, risk_free_rate, log_returns, stock_num)
        movavg_percentages = accounting_for_movavg(percentages, fifty, twohundred, curr_year,curr_end_year, curr_month, curr_end_month)
        macd_signal_normal = macd_signal(MACD, signal_line, curr_year, curr_month, percentages)
        macd_signal_dynamic = macd_signal(MACD, signal_line, curr_year, curr_month, movavg_percentages)
        if count == 0:
            static_percentages = percentages
        #sigmoidal data under this

        static_movavg_percent = accounting_for_movavg(static_percentages, fifty, twohundred, curr_year,curr_end_year, curr_month, curr_end_month)
        macd_signal_static = macd_signal(MACD, signal_line, curr_year, curr_month, static_percentages)
        print("Dynamic: ", end="")
        initial_investment = returns_calculation(percentages, initial_investment, curr_year, curr_end_year, curr_month, curr_end_month, data)
        print("Static: ", end="")
        static_investment = returns_calculation(static_percentages, static_investment, curr_year, curr_end_year, curr_month, curr_end_month, data)
        print("Static with moving average: ", end="")
        static_movavg = returns_calculation(static_movavg_percent, static_movavg, curr_year, curr_end_year, curr_month, curr_end_month, data)
        print("Dynamic with moving average: ", end="")
        dynamic_movavg = returns_calculation(movavg_percentages, dynamic_movavg, curr_year,curr_end_year, curr_month, curr_end_month, data)
        print("Static with macd_signal: ", end="")
        static_macd_signal_investment = returns_calculation(macd_signal_static, static_macd_signal_investment, curr_year, curr_end_year, curr_month, curr_end_month, data)
        print("macd_signal: ", end="")
        macd_signal_investment = returns_calculation(macd_signal_normal, macd_signal_investment, curr_year, curr_end_year, curr_month, curr_end_month, data)
        print("dynamic with macd_signal and movavg: ", end="")
        dynamic_macd_signal_investment = returns_calculation(macd_signal_dynamic, dynamic_macd_signal_investment, curr_year, curr_end_year, curr_month, curr_end_month, data)
        market_value.append(initial_investment)
        static_y.append(static_investment)
        static_ma.append(static_movavg)
        dynamic_ma.append(dynamic_movavg)
        static_macd_signal.append(static_macd_signal_investment)
        dynamic_macd_signal.append(dynamic_macd_signal_investment)
        normal_macd_signal.append(macd_signal_investment)
        month += 1
        if month == 13:
            month = 1
            past_start += 1
            past_end += 1
        curr_month += 1
        curr_end_month += 1
        if curr_end_month == 13:
            curr_end_month = 1
            curr_end_year += 1
        if curr_month == 13:
            curr_month = 1
            curr_year += 1
        count += 1
        counter += 1
        x_values.append(counter)
    return x_values, market_value, static_y, static_ma, dynamic_ma, static_macd_signal, dynamic_macd_signal, normal_macd_signal

if __name__ == "__main__" :
    app = Dash(__name__)

    app.layout = html.Div([
	html.H6("Investment Outlook"),
        dcc.Graph(id='graph-with-slider'),
	html.Br(),
        html.Div([
        " stocks: ",
        dcc.Input( type='text', value="AAPL NFLX GOOGL AMZN", id='stock-slider'),
        " Current year: ",
        dcc.Input( type='number', value=2019, id='current-year-slider'),
        " Initial investment: ",
        dcc.Input( type='number', value=100000, id='investment-slider'),
        html.Button('Submit', id='submit-val', n_clicks=0)
	]),
    ])
    @app.callback(
	Output('graph-with-slider', 'figure'),
	[State('stock-slider', 'value'),
    State('current-year-slider', 'value'),
	State('investment-slider', 'value')],
    Input('submit-val', 'n_clicks'))


    #Input('current-year-slider', 'value'),
	#Input('investment-slider', 'value'),
    #Input('submit-val', 'n_clicks'))


    def update_figure( stocks, year, investment, n_clicks):
        if n_clicks is None:
            raise PreventUpdate
        else:
            stocks = stocks.split(' ')
            print(stocks)
            x_values, y_values, static_y, static_ma, dynamic_ma, static_macd_signal, dynamic_macd_signal, normal_macd_signal = calculations(stocks, year, investment)
            fig = px.line(x=x_values, y=[y_values,static_y, static_ma, dynamic_ma, static_macd_signal, dynamic_macd_signal, normal_macd_signal], template="plotly_dark", markers = True,
            labels={'x':'months', 'y':'return', }) # override keyword names with labels
            newnames = {'wide_variable_0':'Dynamic', 'wide_variable_1': 'Static', 'wide_variable_2': 'Static & MA', 'wide_variable_3': 'Dynamic & MA', 'wide_variable_4': 'Static & macd_signal', 'wide_variable_5': 'Dynamic & macd_signal & MA', 'wide_variable_6': 'Dynamic & macd_signal'}
            fig.for_each_trace(lambda t: t.update(name = newnames[t.name],
                                                  legendgroup = newnames[t.name],
                                                  hovertemplate = t.hovertemplate.replace(t.name, newnames[t.name])
                                                 )
                              )

            fig.update_layout(transition_duration=500)
            return fig

    if __name__ == "__main__":
        app.run_server(debug=True)
