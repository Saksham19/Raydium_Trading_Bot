
####Once we have the filtered pools - next step is - go buy the token

from spl.token.instructions import create_associated_token_account, get_associated_token_address
from spl.token.instructions import close_account, CloseAccountParams
from spl.token.client import Token
from solders.pubkey import Pubkey
from solders.instruction import Instruction
from solana.rpc.types import TokenAccountOpts
from solana.transaction import AccountMeta
from construct import Bytes, Int8ul, Int64ul, BytesInteger
from construct import Struct as cStruct
from spl.token.core import _TokenCore

from dotenv import load_dotenv

from solana.rpc.commitment import Commitment
from solana.rpc.api import RPCException
from solana.rpc.api import Client, Keypair
from solders.compute_budget import set_compute_unit_price,set_compute_unit_limit

import base58

from solders.signature import Signature

from src.components.dexscreener import getSymbol
from src.components.layouts import SWAP_LAYOUT
from src.components.create_close_account import get_token_account, fetch_pool_keys, get_token_account, make_swap_instructions
import time 
import telegram
import asyncio 
import requests
import pandas as pd
import os

load_dotenv()

priv_key = os.getenv('PRIVATE_KEY')
tele_bot_key = os.getenv('tele_bot_token')
tele_chat_id = os.getenv('tele_bot_chat_id')




solana_client  = Client("https://api.mainnet-beta.solana.com")
bot = telegram.Bot(token=f"{tele_bot_key}")


LAMPORTS_PER_SOL = 1000000000

AMM_PROGRAM_ID = Pubkey.from_string('675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8')
SERUM_PROGRAM_ID = Pubkey.from_string('srmqPvymJeFKQ4zGQed1GFppgkRHL9kaELCbyksJtPX')


#myWallet = Pubkey.from_string('En5z1QWHbUtWdd54mdK1QVEBSpvDwejZDkroFAbccXbD')  ###THIS SHOULD BE YOUR WALLET PUB ADDRESS
#mint_address = Pubkey.from_string('Gzwy4DrmumZAG4Mu5m6S2uSKVyZ9GQ3GMAgmTsX4a1kq') ##tyler token   - SHOULD BE THE TOKEN PUB ADDRESS
accountProgramId = solana_client.get_account_info_json_parsed(Pubkey.from_string("Gzwy4DrmumZAG4Mu5m6S2uSKVyZ9GQ3GMAgmTsX4a1kq"))  ###GETS US THE ACC INFO FOR THE MINT ACCOUNT 




LAMPORTS_PER_SOL = 1000000000

def fetch_pool_keys_with_retry(mint, max_retries=5, delay_between_retries=30):
    for attempt in range(max_retries):
        pool_keys = fetch_pool_keys(str(mint))
        if pool_keys != "failed":
            return pool_keys
        else:
            print(f"Attempt {attempt + 1} failed to fetch pool keys for mint {mint}. Retrying...")
            time.sleep(delay_between_retries) # Wait for a bit before retrying

    print(f"Failed to fetch pool keys for mint {mint} after {max_retries} attempts.")
    return "failed"


def buy(solana_client, TOKEN_TO_SWAP_BUY, payer, amount):
    token_symbol, SOl_Symbol = getSymbol(TOKEN_TO_SWAP_BUY)

    mint = Pubkey.from_string(TOKEN_TO_SWAP_BUY)

    pool_keys = fetch_pool_keys_with_retry(mint)


    if pool_keys == "failed":
        print(f"a|BUY Pool ERROR {token_symbol} ", f"[Raydium]: Pool Key Not Found")
        return "failed"

    else:
        # Continue with your logic here
        print("Pool Keys: ", pool_keys)





    """
    Calculate amount
    """
    amount_in = int(amount * LAMPORTS_PER_SOL)
    # slippage = 0.1
    # lamports_amm = amount * LAMPORTS_PER_SOL
    # amount_in =  int(lamports_amm - (lamports_amm * (slippage/100)))

    txnBool = True
    while txnBool:

        """Get swap token program id"""
        print("1. Get TOKEN_PROGRAM_ID...")
        accountProgramId = solana_client.get_account_info_json_parsed(mint)
        TOKEN_PROGRAM_ID = accountProgramId.value.owner

        """
        Set Mint Token accounts addresses
        """
        print("2. Get Mint Token accounts addresses...")
        swap_associated_token_address, swap_token_account_Instructions = get_token_account(solana_client,
                                                                                           payer.pubkey(), mint)

        """
        Create Wrap Sol Instructions
        """
        print("3. Create Wrap Sol Instructions...")
        balance_needed = Token.get_min_balance_rent_for_exempt_for_account(solana_client)
        WSOL_token_account, swap_tx, payer, Wsol_account_keyPair, opts, = _TokenCore._create_wrapped_native_account_args(
            TOKEN_PROGRAM_ID, payer.pubkey(), payer, amount_in,
            False, balance_needed, Commitment("confirmed"))
        """
        Create Swap Instructions
        """
        print("4. Create Swap Instructions...")
        instructions_swap = make_swap_instructions(amount_in,
                                                  WSOL_token_account,
                                                  swap_associated_token_address,
                                                  pool_keys,
                                                  mint,
                                                  solana_client,
                                                  payer
                                                  )
        # print(instructions_swap)

        print("5. Create Close Account Instructions...")
        params = CloseAccountParams(account=WSOL_token_account, dest=payer.pubkey(), owner=payer.pubkey(),
                                    program_id=TOKEN_PROGRAM_ID)
        closeAcc = (close_account(params))

        print("6. Add instructions to transaction...")
        if swap_token_account_Instructions != None:
            swap_tx.add(swap_token_account_Instructions)
        swap_tx.add(set_compute_unit_price(400_000)) #Set your gas fees here in micro_lamports eg 1_000_000 ,20_400_000 choose amount in sol and multiply by microlamport eg 1000000000 =1 lamport

        swap_tx.add(instructions_swap)
        swap_tx.add(closeAcc)




        try:
            print("7. Execute Transaction...")
            start_time = time.time()
            txn = solana_client.send_transaction(swap_tx, payer, Wsol_account_keyPair)
            txid_string_sig = txn.value
            print("Here is the Transaction Signature NB Confirmation is just to wait for confirmation: ", txid_string_sig)

            print("8. Confirm transaction...")

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
            time.sleep(1)
        except Exception as e:
            print(f"e|BUY Exception ERROR {token_symbol} ", f"[Raydium]: {e}")
            print(f"Error: [{e}]...\nEnd...")
            txnBool = False
            return "failed"



async def main_buy(token_address):


    solana_client = Client('https://api.mainnet-beta.solana.com')

    token_toBuy=token_address
    payer = Keypair.from_base58_string(f"{priv_key}") ##priv key here!
    print(payer.pubkey())

    ####WE'll essentially need to calc 20 ish dollars worth of sol at current price

    amount_in,token_symbol,sig = buy(solana_client, token_toBuy, payer, 0.15)

    ###we need to grab the number of tokens here?


    ###basically get sol price here for around 0.15 sol - that's the usd amt we bought


    sol_price = requests.get('https://min-api.cryptocompare.com/data/price?fsym=SOL&tsyms=USD')
    sol_price = sol_price.json()
    sol_price = sol_price['USD']
    token_value = sol_price*0.15

    buy_entry ={}

    await bot.send_message(chat_id=f"{tele_chat_id}",text=f"BUY TRADE: {token_symbol} \n\n AMT: {token_value}")

    ##ADD THE INFO TO PNL CALCS

    buy_entry[token_symbol] = [time.time()*1000,token_symbol,'BUY',token_value]

    try:
        buy_entry_df = pd.DataFrame.from_dict(buy_entry, orient='index')
        buy_entry_df.columns = ['TIMESTAMP', 'SYMBOL','TYPE', 'USD VALUE']
    except:
        buy_entry_df = pd.DataFrame(columns=['TIMESTAMP','SYMBOL','TYPE', 'USD VALUE'])

    trades_df =buy_entry_df

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





#asyncio.run(main_buy('7BgBvyjrZX1YKz4oh9mjb8ZScatkkwb8DzFx7LoiVkM3'))


