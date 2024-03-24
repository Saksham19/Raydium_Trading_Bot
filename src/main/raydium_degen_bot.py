import requests
import pandas as pd
from src.components.buy import main_buy
from src.components.sell import main_sell
from datetime import datetime,timedelta
import pytz
import time
import asyncio

###first, we filter based on basic



filtered_pools = []


continue_trading = True
while continue_trading:
	for m in range(1,11):

		####we get new raydium pools - and filter them down
		res = requests.get(f'https://api.geckoterminal.com/api/v2/networks/solana/new_pools?page={m}')
		data = res.json()

		date_created = []
		pool_name = []
		pool_address = []
		pool_buys_m5 = []
		pool_sells_m5 = []
		pool_buyers_m5 = []
		pool_sellers_m5 = []
		pool_price_change_m5 = []
		pool_price_change_h1 = []
		pool_price_change_h24 = []
		pool_vol_m5 = []
		pool_vol_h1 = []


		for i in range(len(data['data'])):
			date_created.append(data['data'][i]['attributes']['pool_created_at'])
			pool_name.append(data['data'][i]['attributes']['name'])
			pool_address.append(data['data'][i]['attributes']['address'])
			pool_buys_m5.append(data['data'][i]['attributes']['transactions']['m5']['buys'])
			pool_sells_m5.append(data['data'][i]['attributes']['transactions']['m5']['sells'])
			pool_buyers_m5.append(data['data'][i]['attributes']['transactions']['m5']['buyers'])
			pool_sellers_m5.append(data['data'][i]['attributes']['transactions']['m5']['sellers'])
			pool_price_change_m5.append(data['data'][i]['attributes']['price_change_percentage']['m5'])
			pool_price_change_h1.append(data['data'][i]['attributes']['price_change_percentage']['h1'])
			pool_price_change_h24.append(data['data'][i]['attributes']['price_change_percentage']['h24'])
			pool_vol_m5.append(data['data'][i]['attributes']['volume_usd']['m5'])
			pool_vol_h1.append(data['data'][i]['attributes']['volume_usd']['h1'])


			combined_pool_df = pd.concat([pd.DataFrame(date_created),pd.DataFrame(pool_name),pd.DataFrame(pool_address),pd.DataFrame(pool_buys_m5),pd.DataFrame(pool_sells_m5),pd.DataFrame(pool_buyers_m5),pd.DataFrame(pool_sellers_m5),pd.DataFrame(pool_price_change_m5),pd.DataFrame(pool_price_change_h1),pd.DataFrame(pool_price_change_h24),pd.DataFrame(pool_vol_m5),pd.DataFrame(pool_vol_h1)],axis=1)
			combined_pool_df.columns = ['DATE','POOL_NAME','POOL_ADDRESS','BUYS_M5','SELLS_M5','BUYERS_M5','SELLERS_M5','% CHG M5','% CHG H1','% CHG H24','VOL_M5','VOL_H24']

			combined_pool_df.index = pd.to_datetime(combined_pool_df['DATE'])
			combined_pool_df = combined_pool_df.drop(['DATE'],axis=1)


		#####FILTERS HERE


		###FILTER 1  - drop tokens with 0 buys or sells in the last 5 mins

		combined_pool_df = combined_pool_df[combined_pool_df['BUYS_M5']!=0]
		combined_pool_df = combined_pool_df[combined_pool_df['SELLS_M5']!=0]



		# ###FILTER 2 = buys/sells has to be >1
		# combined_pool_df['BUYS_M5'] = combined_pool_df['BUYS_M5'].astype('float')
		# combined_pool_df['SELLS_M5'] = combined_pool_df['SELLS_M5'].astype('float')

		# combined_pool_df['BUY/SELL_M5'] = combined_pool_df['BUYS_M5']/combined_pool_df['SELLS_M5']
		# combined_pool_df = combined_pool_df[combined_pool_df['BUY/SELL_M5']>1]

		# combined_pool_df = combined_pool_df.sort_values(by='BUY/SELL_M5',ascending=False)



		###filter 3 - % chg m5 >0  and %chg h1 >10
		combined_pool_df['% CHG M5'] = combined_pool_df['% CHG M5'].astype('float')
		combined_pool_df = combined_pool_df[combined_pool_df['% CHG M5']>=7]



		###filter 4 - drop any pools with the name N/A?

		combined_pool_df = combined_pool_df[combined_pool_df['POOL_NAME']!='N/A / SOL']




		###filter 5 - should filter by volume - min >=500?
		combined_pool_df['VOL_M5'] = combined_pool_df['VOL_M5'].astype('float')

		combined_pool_df = combined_pool_df[combined_pool_df['VOL_M5']>=3000]


		#####okay so we should probably add in the date at which the pool was created

		###filter 6 - let's keep entries created within the last 10 mins

		combined_pool_df = combined_pool_df.sort_index()

		cutoff_datetime = datetime.now(pytz.utc) - timedelta(minutes=30)
#		cutoff_datetime_end = datetime.now(pytz.utc) - timedelta(minutes=60)

		# Filter rows where index is within the last 10 minutes
		combined_pool_df = combined_pool_df[combined_pool_df.index < cutoff_datetime]
#		combined_pool_df = combined_pool_df[combined_pool_df.index > cutoff_datetime_end]

		print(combined_pool_df)



		try:
			filtered_pools.append(combined_pool_df['POOL_ADDRESS'].values[0])
		except:
			pass


	##we drop duplicates addresses
	filtered_pools  = list(set(filtered_pools))

	print(filtered_pools)


	##then we check orderbook data

	filtered_pools_final = {}

	if filtered_pools is not None:
		for f in filtered_pools:

			res = requests.get(f'https://api.geckoterminal.com/api/v2/networks/solana/pools/{f}/trades')
			data = res.json()

			#print(data)


			date = []
			order_type = []
			from_token_amt = []
			to_token_amt = []
			price_from_in_usd = []
			price_to_in_usd = []


			try:
				for i in range(len(data['data'])):
					date.append(data['data'][i]['attributes']['block_timestamp'])
					order_type.append(data['data'][i]['attributes']['kind'])
					from_token_amt.append(data['data'][i]['attributes']['from_token_amount'])
					to_token_amt.append(data['data'][i]['attributes']['to_token_amount'])
					price_from_in_usd.append(data['data'][i]['attributes']['price_from_in_usd'])
					price_to_in_usd.append(data['data'][i]['attributes']['price_to_in_usd'])
			except:
				print('API LIMIT REACHED')
				print('RESTARTING IN 1 MINUTE')
				time.sleep(60)
				continue


			orderbook_df = pd.concat([pd.DataFrame(date),pd.DataFrame(order_type),pd.DataFrame(from_token_amt),pd.DataFrame(to_token_amt),pd.DataFrame(price_from_in_usd),pd.DataFrame(price_to_in_usd)],axis=1)
			orderbook_df.columns = ['DATE','TYPE','FROM','TO','FROM_USD','TO_USD']

			orderbook_df['FROM'] = orderbook_df['FROM'].astype('float')
			orderbook_df['TO'] = orderbook_df['TO'].astype('float')
			orderbook_df['FROM_USD'] = orderbook_df['FROM_USD'].astype('float')
			orderbook_df['TO_USD'] = orderbook_df['TO_USD'].astype('float')


			orderbook_df['FROM_AMT'] = orderbook_df['FROM']*orderbook_df['FROM_USD']
			#orderbook_df['TO_AMT'] = orderbook_df['TO']*orderbook_df['TO_USD']

			orderbook_df = orderbook_df.drop(['FROM','TO','FROM_USD','TO_USD'],axis=1)

			#	orderbook_df = orderbook_df.tail(30)

			###group by type
			orderbook_df = orderbook_df.groupby('TYPE')['FROM_AMT'].sum()
			buy_sum = orderbook_df.get('buy', 0)
			sell_sum = orderbook_df.get('sell', 0)
			ratio_buy_sell = buy_sum / sell_sum if sell_sum != 0 else float('inf')

			if ratio_buy_sell>=1.2:
				filtered_pools_final[f] = ratio_buy_sell


	####we want to go for pools with orderbook ratio >=1

	#####WE choose the final pool based on two criterias - higher ratio  + more recently created

	try:
		selected_pool =  max(filtered_pools_final, key=lambda k: filtered_pools_final[k])
		print(selected_pool)
	except:
		print('no pool worth trading')
		print('restarting search')
		time.sleep(60)
		continue





	#######trading here

	####we need the token address

	#selected_pool = 'DkVN7RKTNjSSER5oyurf3vddQU2ZneSCYwXvpErvTCFA'

	token_address = requests.get(f'https://api.geckoterminal.com/api/v2/networks/solana/pools/{selected_pool}')
	token_address = token_address.json()
	token_address = token_address['data']['relationships']['base_token']['data']['id']
	token_address = token_address.replace('solana_','')
	print(token_address)

	###first, we initiate the buy order


	asyncio.run(main_buy(token_address))

	###essentially - as long as the orderbook ratio change >1 - we stay in


	#####nope - we switch it profitability - as soon as we hit the 20% mark - we are out of a trade

	token_toSell = token_address
	token_price = requests.get(
		f'https://api.geckoterminal.com/api/v2/simple/networks/solana/token_price/{token_toSell}')
	token_price = token_price.json()
	token_price = token_price['data']['attributes']['token_prices']
	entry_price = float(token_price[token_toSell])

	profit = True
	while profit:
		time.sleep(30)
		token_price = requests.get(
			f'https://api.geckoterminal.com/api/v2/simple/networks/solana/token_price/{token_toSell}')
		token_price = token_price.json()
		token_price = token_price['data']['attributes']['token_prices']
		token_price = float(token_price[token_toSell])

		if ((token_price / entry_price)-1)*100 > 0:
			print('in profit')
			print(token_price / entry_price)
		elif ((token_price/entry_price)-1)*100 <=-7:
			print('loss')
			asyncio.run(main_sell(token_address))
			profit = False

		elif ((token_price / entry_price) - 1) * 100 >= 15:
			print('profit hit. get out')
			asyncio.run(main_sell(token_address))
			profit = False






	# orderbook = True
	# ratio_values = []
	# while orderbook:
	#
	# 	res = requests.get(f'https://api.geckoterminal.com/api/v2/networks/solana/pools/{selected_pool}/trades')
	# 	data = res.json()
	#
	# 	#print(data)
	#
	#
	# 	date = []
	# 	order_type = []
	# 	from_token_amt = []
	# 	to_token_amt = []
	# 	price_from_in_usd = []
	# 	price_to_in_usd = []
	#
	#
	#
	# 	for i in range(len(data['data'])):
	# 		date.append(data['data'][i]['attributes']['block_timestamp'])
	# 		order_type.append(data['data'][i]['attributes']['kind'])
	# 		from_token_amt.append(data['data'][i]['attributes']['from_token_amount'])
	# 		to_token_amt.append(data['data'][i]['attributes']['to_token_amount'])
	# 		price_from_in_usd.append(data['data'][i]['attributes']['price_from_in_usd'])
	# 		price_to_in_usd.append(data['data'][i]['attributes']['price_to_in_usd'])
	#
	#
	#
	# 	orderbook_df = pd.concat([pd.DataFrame(date),pd.DataFrame(order_type),pd.DataFrame(from_token_amt),pd.DataFrame(to_token_amt),pd.DataFrame(price_from_in_usd),pd.DataFrame(price_to_in_usd)],axis=1)
	# 	orderbook_df.columns = ['DATE','TYPE','FROM','TO','FROM_USD','TO_USD']
	#
	# 	orderbook_df['FROM'] = orderbook_df['FROM'].astype('float')
	# 	orderbook_df['TO'] = orderbook_df['TO'].astype('float')
	# 	orderbook_df['FROM_USD'] = orderbook_df['FROM_USD'].astype('float')
	# 	orderbook_df['TO_USD'] = orderbook_df['TO_USD'].astype('float')
	#
	#
	# 	orderbook_df['FROM_AMT'] = orderbook_df['FROM']*orderbook_df['FROM_USD']
	# 	#orderbook_df['TO_AMT'] = orderbook_df['TO']*orderbook_df['TO_USD']
	#
	# 	orderbook_df = orderbook_df.drop(['FROM','TO','FROM_USD','TO_USD'],axis=1)
	#
	# #	orderbook_df = orderbook_df.tail(30)
	#
	# 	###group by type
	# 	orderbook_df = orderbook_df.groupby('TYPE')['FROM_AMT'].sum()
	# 	buy_sum = orderbook_df.get('buy', 0)
	# 	sell_sum = orderbook_df.get('sell', 0)
	# 	ratio_buy_sell = buy_sum / sell_sum if sell_sum != 0 else float('inf')
	#
	# 	print(ratio_buy_sell)
	# 	ratio_values.append(ratio_buy_sell)
	# 	if ratio_buy_sell<1.05:
	# 		asyncio.run(main_sell(token_address))
	# 		break
	#
	# 	elif len(ratio_values)>=12:
	# 		if ratio_values[-1] == ratio_values[-6]:
	# 			print(ratio_values)
	# 			asyncio.run(main_sell(token_address))
	# 			break
	# 		######let's do a drop in percent chg as a criteria for exiting
	# 		elif ratio_values[-1] <=1.5:
	# 			if (ratio_values[-1] / ratio_values[-2]) <= 0.75:
	# 				asyncio.run(main_sell(token_address))
	# 				break
	#
	#
	# 	time.sleep(15)
	#
	#
	#
