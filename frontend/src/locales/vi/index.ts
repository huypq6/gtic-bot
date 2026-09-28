// Vietnamese dictionary: English source string → Vietnamese. One file per UI area.
import accountBacktest from "./accountBacktest";
import common from "./common";
import misc from "./misc";
import tradingOrders from "./tradingOrders";

export const VI: Record<string, string> = {
  ...misc,
  ...tradingOrders,
  ...accountBacktest,
  ...common,
};
