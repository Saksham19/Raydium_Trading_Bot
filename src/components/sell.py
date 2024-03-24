from spl.token.instructions import close_account, CloseAccountParams

from solana.rpc.types import TokenAccountOpts
from solana.rpc.api import RPCException
from solana.transaction import Transaction

from solders.pubkey import Pubkey
from solana.rpc.api import Client, Keypair
import base58
from solders.compute_budget import set_compute_unit_price,set_compute_unit_limit
from src.components.create_close_account import fetch_pool_keys, sell_get_token_account, get_token_account, \
    make_swap_instructions
from src.components.dexscreener import getSymbol
# from webhook import sendWebhook

import time
import telegram
import asyncio 
import requests
import pandas as pd
import os
from dotenv import load_dotenv


LAMPORTS_PER_SOL = 1000000000


load_dotenv()

priv_key = os.getenv('PRIVATE_KEY')
tele_bot_key = os.getenv('tele_bot_token')
tele_chat_id = os.getenv('tele_bot_chat_id')



bot = telegram.Bot(token=f"{tele_bot_key}")




# ctx ,     TOKEN_TO_SWAP_SELL,  keypair
def sell(solana_client, TOKEN_TO_SWAP_SELL, payer):
    token_symbol, SOl_Symbol = getSymbol(TOKEN_TO_SWAP_SELL)

    mint = Pubkey.from_string(TOKEN_TO_SWAP_SELL)
    sol = Pubkey.from_string("So11111111111111111111111111111111111111112")

    """Get swap token program id"""
    print("1. Get TOKEN_PROGRAM_ID...")
    TOKEN_PROGRAM_ID = solana_client.get_account_info_json_parsed(mint).value.owner

    """Get Pool Keys"""
    print("2. Get Pool Keys...")
    pool_keys = fetch_pool_keys(str(mint))
    if pool_keys == "failed":
        print(f"a|Sell Pool ERROR {token_symbol}", f"[Raydium]: Pool Key Not Found")
        return "failed"

    txnBool = True
    while txnBool:
        """Get Token Balance from wallet"""
        print("3. Get oken Balance from wallet...")

        balanceBool = True
        while balanceBool:
            tokenPk = mint

            accountProgramId = solana_client.get_account_info_json_parsed(tokenPk)
            programid_of_token = accountProgramId.value.owner

            accounts = solana_client.get_token_accounts_by_owner_json_parsed(payer.pubkey(), TokenAccountOpts(
                program_id=programid_of_token)).value
            for account in accounts:
                mint_in_acc = account.account.data.parsed['info']['mint']
                if mint_in_acc == str(mint):
                    amount_in = int(account.account.data.parsed['info']['tokenAmount']['amount'])
                    print("3.1 Token Balance [Lamports]: ", amount_in)
                    break
            if int(amount_in) > 0:
                balanceBool = False
            else:
                print("No Balance, Retrying...")
                time.sleep(2)

        """Get token accounts"""
        print("4. Get token accounts for swap...")
        swap_token_account = sell_get_token_account(solana_client, payer.pubkey(), mint)
        WSOL_token_account, WSOL_token_account_Instructions = get_token_account(solana_client, payer.pubkey(), sol)

        if swap_token_account == None:
            print("swap_token_account not found...")
            return "failed"

        else:
            """Make swap instructions"""
            print("5. Create Swap Instructions...")
            instructions_swap = make_swap_instructions(amount_in,
                                                      swap_token_account,
                                                      WSOL_token_account,
                                                      pool_keys,
                                                      mint,
                                                      solana_client,
                                                      payer
                                                      )

            """Close wsol account"""
            print("6.  Create Instructions to Close WSOL account...")
            params = CloseAccountParams(account=WSOL_token_account, dest=payer.pubkey(), owner=payer.pubkey(),
                                        program_id=TOKEN_PROGRAM_ID)
            closeAcc = (close_account(params))

            """Create transaction and add instructions"""
            print("7. Create transaction and add instructions to Close WSOL account...")
            swap_tx = Transaction()
            signers = [payer]
            if WSOL_token_account_Instructions != None:
                swap_tx.add(WSOL_token_account_Instructions)
            swap_tx.add(instructions_swap)
            swap_tx.add(closeAcc)


            ##lets set fees here too
            swap_tx.add(set_compute_unit_price(400_000)) #Set your gas fees here in micro_lamports eg 1_000_000 ,20_400_000 choose amount in sol and multiply by microlamport eg 1000000000 =1 lamport



            """Send transaction"""
            try:
                print("8. Execute Transaction...")
                start_time = time.time()
                txn = solana_client.send_transaction(swap_tx, *signers)

                """Confirm it has been sent"""
                txid_string_sig = txn.value
                print("9. Confirm it has been sent...")
                print("Transaction Signature: ", txid_string_sig)

                confirmed_txn = solana_client.confirm_transaction(txid_string_sig)
                if confirmed_txn:
                    print("Transaction Success")
                    end_time = time.time()
                    execution_time = end_time - start_time
                    print(f"Execution time: {execution_time} seconds")
                    txnBool = False
                    return amount_in, token_symbol, txid_string_sig
                else:
                    print("Transaction Failed")
                    end_time = time.time()
                    execution_time = end_time - start_time
                    print(f"Execution time: {execution_time} seconds")
                    txnBool = False

            except RPCException as e:
                print(f"Error: [{e.args[0].message}]...\nRetrying...")
                time.sleep(30)
            except Exception as e:
                print(f"e|SELL Exception ERROR {token_symbol} ", f"[Raydium]: {e}")
                print(f"Error: [{e}]...\nEnd...")
                txnBool = False
                return "failed"

solana_client = Client('https://api.mainnet-beta.solana.com')



async def main_sell(token_address):

    token_toSell= token_address #Enter Token Address to Sell


    private_key_string = f"{priv_key}" ###priv key here - dont hardcode!!!!!
    private_key_bytes = base58.b58decode(private_key_string)
    payer = Keypair.from_bytes(private_key_bytes)
    print(f"Your Wallet Address : {payer.pubkey()}")
    amount_in,token_symbol,sig = sell(solana_client,token_toSell,payer)

    ###we'll need to calc the usd value of the ticker here 
    ##we know the quantity of tokens (amount_in) - just need to multiply that by usd price

    token_price = requests.get(f'https://api.geckoterminal.com/api/v2/simple/networks/solana/token_price/{token_toSell}')
    token_price = token_price.json()
    token_price = token_price['data']['attributes']['token_prices']
    token_price = float(token_price[token_toSell])
    token_price = token_price*(amount_in/1000000)

    await bot.send_message(chat_id=f"{tele_chat_id}",text=f"SELL TRADE: {token_symbol} \n\n AMT: {token_price}")

    ##ADD THE INFO TO PNL CALCS


    sell_entry ={}

    sell_entry[token_symbol] = [time.time()*1000,token_symbol,'SELL',token_price]

    try:
        sell_entry_df = pd.DataFrame.from_dict(sell_entry, orient='index')
        sell_entry_df.columns = ['TIMESTAMP', 'SYMBOL','TYPE', 'USD VALUE']
    except:
        sell_entry_df = pd.DataFrame(columns=['TIMESTAMP','SYMBOL','TYPE', 'USD VALUE'])

    trades_df =sell_entry_df

    print(trades_df)

    ####APPEND THIS TO THE EXISTING TRADES EXCEL FILE

    cwd = os.getcwd()
    cwd = r'E:\\Sol_Pool_Models\\Raydium Bot\\src\\components'

    # Specify the existing Excel file and sheet name
    excel_file_path = cwd+'/raydium_trades.xlsx'
    sheet_name = 'Sheet1'  # Change this to your actual sheet name

    # Read the existing Excel file into a DataFrame
    existing_df = pd.read_excel(excel_file_path, sheet_name=sheet_name)


    try:
        existing_df.index = existing_df['SYMBOL']
        existing_df = existing_df.drop(['SYMBOL'], axis=1)
    except:
        pass

    # Append the new DataFrame to the existing DataFrame
    merged_df = pd.concat([existing_df, trades_df], ignore_index=False)
    merged_df['SYMBOL'] = merged_df.index

    print(merged_df)    
    merged_df = merged_df.reset_index()
    merged_df = merged_df.drop(['index'], axis=1)

    # # Write the merged DataFrame back to the Excel file, starting from the first non-empty row
    # with pd.ExcelWriter(excel_file_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
    #     merged_df.to_excel(writer, sheet_name=sheet_name, startrow=first_non_empty_row, index=False)


    merged_df.to_excel(cwd+'/raydium_trades.xlsx', index=False)




    ##DO PNL CALCS

    df = pd.read_excel(cwd+'/raydium_trades.xlsx')

    ###filter tradeds that have both BUY and SELL

    valid_symbols = df[df['TYPE'].isin(['BUY', 'SELL'])].groupby('SYMBOL')['TYPE'].nunique() == 2
    valid_symbols = valid_symbols[valid_symbols].index
    valid_trades = df[df['SYMBOL'].isin(valid_symbols)]

    # Identify the rows where the trade is a buy
    buy_rows = valid_trades[valid_trades['TYPE'] == 'BUY']

    # Identify the corresponding sell trades for each buy trade
    sell_rows = valid_trades[valid_trades['TYPE'] == 'SELL']

    # Find the last sell trade for each symbol
    last_sell_for_symbol = sell_rows.groupby('SYMBOL')['TIMESTAMP'].max()

    # Filter out the buy trades where there is no corresponding sell trade
    df_filtered = buy_rows[~((buy_rows['SYMBOL'].isin(last_sell_for_symbol.index)) &
                            (buy_rows['TIMESTAMP'] < last_sell_for_symbol[buy_rows['SYMBOL']].values))]
    valid_trades = valid_trades.drop(df_filtered.index)

    # Calculate P&L
    valid_trades['P&L'] = 0
    valid_trades.loc[valid_trades['TYPE'] == 'BUY', 'P&L'] = -valid_trades['USD VALUE']
    valid_trades.loc[valid_trades['TYPE'] == 'SELL', 'P&L'] = valid_trades['USD VALUE']

    # Calculate overall P&L
    overall_pnl_usd = valid_trades['P&L'].sum()

    # Calculate percentage gain/loss by symbol
    total_buys = valid_trades[valid_trades['TYPE'] == 'BUY'].groupby('SYMBOL')['USD VALUE'].sum()
    total_sells = valid_trades[valid_trades['TYPE'] == 'SELL'].groupby('SYMBOL')['USD VALUE'].sum()
    percentage_pnl_by_symbol = ((total_sells - total_buys) / total_buys) * 100

    # Calculate overall P&L percentage
    overall_pnl_percentage = percentage_pnl_by_symbol.sum()

    # Display the DataFrame with P&L information for valid trades
    print(valid_trades)

    # Display overall P&L and P&L percentages
    print("Overall P&L in USD:", overall_pnl_usd)
    print("Overall P&L Percentage:", overall_pnl_percentage)

    # Display percentage gain/loss by symbol
    print("\nPercentage Gain/Loss by Symbol:")
    percentage_pnl_by_symbol = percentage_pnl_by_symbol.round(2)
    print(percentage_pnl_by_symbol)



    await bot.send_message(chat_id=f"{tele_chat_id}", text=f"{percentage_pnl_by_symbol.to_markdown(index=True)}")
    await bot.send_message(chat_id=f"{tele_chat_id}", text=f"Overall %: {overall_pnl_percentage}")








    ###will need to add PNL calcs here 

#asyncio.run(main_sell('6fPwmaHvtSZ1mCM8XjcUNN6J6TP67h3vP4m8MiPvfQK6'))
