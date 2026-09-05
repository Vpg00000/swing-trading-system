from abc import ABC, abstractmethod
import math

class SlippageModel(ABC):
    @abstractmethod
    def calculate_slippage(self, order_quantity: float, current_price: float, is_buy: bool) -> float:
        """
        Calculates the slippage amount for a given order.

        Args:
            order_quantity: The absolute quantity of the order (e.g., number of shares).
            current_price: The current market price before the order.
            is_buy: True if it's a buy order, False if it's a sell order.

        Returns:
            The price adjustment due to slippage. For a buy order, this will be
            added to the price (positive). For a sell order, it will be
            subtracted from the price (negative, as the actual sell price decreases).
        """
        pass

class SquareRootSlippageModel(SlippageModel):
    def __init__(self, k_factor: float, base_quantity: float = 1.0):
        """
        Initializes the SquareRootSlippageModel.

        Args:
            k_factor: The sensitivity factor for market impact.
                      A higher k_factor implies greater market impact.
                      This factor determines the percentage price impact for a trade
                      of size `base_quantity`. For example, if k_factor is 0.001
                      and base_quantity is 1, a trade of 1 unit will incur 0.1% price impact.
            base_quantity: A normalizing quantity, often set to 1 or a typical market block size.
                         Used in the square root calculation to scale the order size.
                         Must be positive.
        """
        if k_factor < 0:
            raise ValueError("k_factor must be non-negative.")
        if base_quantity <= 0:
            raise ValueError("base_quantity must be positive.")
        self._k_factor = k_factor
        self._base_quantity = base_quantity

    def calculate_slippage(self, order_quantity: float, current_price: float, is_buy: bool) -> float:
        """
        Calculates the slippage based on a non-linear square-root market impact model.
        The price impact is proportional to k_factor * sqrt(order_quantity / base_quantity) * current_price.

        Args:
            order_quantity: The absolute quantity of the order (e.g., number of shares).
            current_price: The current market price before the order.
            is_buy: True if it's a buy order, False if it's a sell order.

        Returns:
            The price adjustment due to slippage. For a buy order, this will be
            added to the price (positive). For a sell order, it will be
            subtracted from the price (negative).
        """
        if order_quantity <= 0:
            return 0.0

        # Calculate the impact magnitude
        # The impact is expressed as a percentage of the current price.
        # k_factor * sqrt(order_quantity / base_quantity) gives the percentage change.
        impact_percentage = self._k_factor * math.sqrt(order_quantity / self._base_quantity)
        price_impact_magnitude = impact_percentage * current_price

        # Apply direction
        if is_buy:
            return price_impact_magnitude
        else: # is_sell
            return -price_impact_magnitude