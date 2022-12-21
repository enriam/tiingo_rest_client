# Class Tiingo Client
# Connects to tiingo.com to get financial instruments data
# https://github.com/enriam

import requests
import re
from typing import Sequence, TypeVar, Union
import pandas as pd
from datetime import date
from io import StringIO

JSON = TypeVar("JSON")  # used for json type hint


class TiingoError(Exception):
    """Wrapper for TiingoClient exceptions."""

    pass


class TiingoRESTClient:
    """REST client used to connect and retrieve data from tiingo.com"""

    # --- REST endpoints
    # end of day data
    _tii_eod = "https://api.tiingo.com/tiingo/daily/"
    # intraday data
    _tii_iex = "https://api.tiingo.com/iex/"

    # --- Column names
    # end of day data
    _tii_eod_cols = (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "adjOpen",
        "adjHigh",
        "adjLow",
        "adjClose",
        "adjVolume",
        "divCash",
        "splitFactor",
    )
    # iex intraday historical data
    _tii_iex_hist_cols = (
        "open",
        "high",
        "low",
        "close",
        "volume",
    )
    # iex intraday last price data
    _tii_iex_last_cols = (
        "timestamp",
        "quoteTimestamp",
        "lastSaleTimestamp",
        "last",
        "lastSize",
        "tngoLast",
        "prevClose",
        "open",
        "high",
        "low",
        "mid",
        "volume",
        "bidSize",
        "bidPrice",
        "askSize",
        "askPrice",
    )

    # --- Resample frequencies
    # fixed frequencies (eod endpoint)
    _tii_resample_freqs = ("daily", "weekly", "monthly", "annually")
    # pattern frequencies (iex endpoint)
    _tii_resample_pattern = "\A^[0-9]+(min|hour)\Z"

    def __init__(self, token):
        self._tii_headers = {
            "Content-Type": "application/json",
            "Authorization": "Token " + str(token),
        }
        # validate token
        r = requests.get(
            f"https://api.tiingo.com/api/test?token={token}",
            headers=self._tii_headers,
        ).json()
        if r["message"] == "Auth Token was not correct":
            raise TiingoError(
                f'Tiingo rejected Auth Token "{token}".\n'
                f"Tiingo response: {r}"
            )

    def __repr__(self):
        return f"<TiingoRESTClient(https://api.tiingo.com)>"

    # --- Tools
    def _is_valid_date(self, str_date):
        """Check if date string is a valid ISO format"""
        # empty string is valid
        if str_date == "":
            return True
        # validate ISO format
        try:
            date.fromisoformat(str_date)
        except:
            return False
        else:
            return True

    def _validate_cols(self, endpoint, columns):
        """Returns a list with only valid column names"""

        # identify set of valid names based on endpoint
        if endpoint == "eod":
            valid_names = self._tii_eod_cols
        elif endpoint == "iex_last":
            valid_names = self._tii_iex_last_cols
        elif endpoint == "iex_hist":
            valid_names = self._tii_iex_hist_cols
        else:
            print(
                f"WARNING: could not proceed with column names validation. "
                + "Wil return all available columns from Tiingo."
            )
            return []

        # select and return only valid column names
        valid_columns = []
        for column in columns:
            if column in valid_names:
                valid_columns.append(column)
            else:
                print(
                    f'WARNING: column name "{column}" is invalid and '
                    + "was removed from list of columns."
                )
        return valid_columns

    def _build_pre_query(self, endpoint, columns, start, end, resample):
        """Builds a pre query that will not work until word 'ticker'
        is replaced by real ticker"""

        # define query components
        format = "format=json"  # so far this is not a user option
        cols = "&columns=" + ",".join(columns) if columns else ""
        freq = "&resampleFreq=" + resample
        start_date = "&startDate=" + start if start else ""
        end_date = "&endDate=" + end if end else ""

        # build and return pre query
        return (
            f"{endpoint}ticker/prices?{format}"
            f"{freq}{cols}{start_date}{end_date}"
        )

    # --- Methods
    def get_stock_metadata(self, ticker: str) -> JSON:
        """Returns ticker metadata in json format"""
        tii_request = f"{self._tii_eod}{ticker}"
        r = requests.get(tii_request, headers=self._tii_headers)
        return r.json()

    def get_stock_hist(
        self,
        tickers: Union[str, Sequence[str]],
        frequency: str,
        start: str = "",
        end: str = "",
        columns: Sequence[str] = [],
    ) -> pd.DataFrame:
        """Returns a dataframe with historical data for all tickers"""

        # --- Data Validation
        # tickers
        if isinstance(tickers, str):
            tickers = [tickers]
        # resample frequency and column names
        # case 1: iex data
        if re.match(self._tii_resample_pattern, frequency):
            end_point = self._tii_iex
            valid_columns = self._validate_cols("iex_hist", columns)
        # case 2: eod data
        elif frequency in self._tii_resample_freqs:
            end_point = self._tii_eod
            valid_columns = self._validate_cols("eod", columns)
        # case 3: wrong data
        else:
            err_msg = (
                f'Invalid resample frequency: "{frequency}".\n'
                "\tValid values:\n"
                f"\t - End of day data: {self._tii_resample_freqs}\n"
                "\t - Intraday data: 5min, 15min, 1hour, 4hour, etc."
            )
            raise TiingoError(err_msg)

        # start and end dates
        if not self._is_valid_date(start) or not self._is_valid_date(end):
            err_msg = f'Invalid date format. Valid format is: "YYYY-MM-DD"'
            raise TiingoError(err_msg)

        # --- Data Retrieval
        # build pre query (instead of ticker value will have 'ticker' literal)
        tii_request = self._build_pre_query(
            end_point, valid_columns, start, end, frequency
        )
        # create list to hold dataframes
        data = []
        # create list to hold valid tickers (don't get error from tiingo)
        valid_tickers = []
        # request data, open a session for higher performance
        with requests.Session() as s:
            s.headers.update(self._tii_headers)
            for ticker in tickers:
                # send request using ticker values
                r = s.get(tii_request.replace("ticker", ticker))
                # convert to dataframe and add to dataframe list
                try:
                    px = pd.read_json(StringIO(r.text))
                except:
                    print(
                        f'WARNING: request for "{ticker.upper()}" returned '
                        + "an error and was removed from list of tickers."
                        f"\nTiingo response: {r.json()}\n"
                    )
                else:
                    px.set_index("date", inplace=True)
                    valid_tickers.append(ticker)
                    data.append(px)

        # --- Dataframe composition
        # case 1: list of dataframes is empty -> return empty dataframe
        if len(data) == 0:
            df = pd.DataFrame()
        # case 2: there is only one dataframe -> return it
        elif len(data) == 1:
            df = data[0]
        # case 3: several dataframes with only one column -> concat axis = 1
        elif len(columns) == 1:
            df = pd.concat(data, axis=1, names=["ticker"])
            df.columns = valid_tickers
        # case 4: several dataframes with several columns -> concat axis = 0
        else:
            df = pd.concat(data, keys=valid_tickers, names=["ticker"])

        return df

    def get_stock_last(
        self, tickers: Union[str, Sequence[str]], columns: Sequence[str] = []
    ) -> pd.DataFrame:
        """Returns a dataframe with last available data"""

        # tickers
        if isinstance(tickers, str):
            tickers = [tickers]

        # --- Build query
        # tickers
        tickers_str = ",".join(tickers)
        http_req = f"{self._tii_iex}?tickers={tickers_str}&format=csv"

        # columns
        #   Note: the following functionality (specifiying several columns
        #   to be retrieved) is not documented in Tiingo, but it works. In
        #   the future this could change.
        valid_columns = self._validate_cols(
            endpoint="iex_last", columns=columns
        )
        if valid_columns:
            columns_str = ",".join(valid_columns)
            http_req += f"&columns={columns_str}"

        # --- Request data
        r = requests.get(http_req, headers=self._tii_headers)
        px = pd.read_csv(StringIO(r.text), index_col="ticker")
        return px
