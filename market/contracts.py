__author__ = 'chris'

import json
import bitcoin
import random
from hashlib import sha256
from binascii import unhexlify, hexlify
from collections import OrderedDict
from urllib2 import Request, urlopen, URLError

import re
import os
import nacl.encoding
from twisted.internet import reactor
from protos.objects import Listings
from protos.countries import CountryCode
from dht.utils import digest
from constants import DATA_FOLDER
from db.datastore import HashMap, ListingsStore, ModeratorStore
from market.profile import Profile
from keyutils.keys import KeyChain
from keyutils.bip32utils import derive_childkey


class Contract(object):
    """
    A class for creating and interacting with OpenBazaar Ricardian contracts.
    """

    def __init__(self, contract=None, hash_value=None, testnet=False):
        """
        This class can be instantiated with either an `OrderedDict` or a hash
        of a contract. If a hash is used, we will load the contract from either
        the file system or cache.

        Alternatively, pass in no parameters if the intent is to create a new
        contract.

        Args:
            contract: an `OrderedDict` containing a filled out json contract
            hash: a hash160 (in raw bytes) of a contract
            testnet: is this contract on the testnet
        """
        if contract is not None:
            self.contract = contract
        elif hash_value is not None:
            try:
                file_path = HashMap().get_file(hash_value)
                if file_path is None:
                    file_path = DATA_FOLDER + "cache/" + hexlify(hash_value)
                with open(file_path, 'r') as filename:
                    self.contract = json.load(filename, object_pairs_hook=OrderedDict)
            except Exception:
                self.contract = {}
        else:
            self.contract = {}

        # used when purchasing this contract
        self.testnet = testnet
        self.ws = None
        self.blockchain = None
        self.amount_funded = 0
        self.received_txs = []
        self.timeout = None

    def create(self,
               expiration_date,
               metadata_category,
               title,
               description,
               currency_code,
               price,
               process_time,
               nsfw,
               shipping_origin,
               shipping_regions,
               est_delivery_domestic=None,
               est_delivery_international=None,
               terms_conditions=None,
               returns=None,
               keywords=None,
               category=None,
               condition=None,
               sku=None,
               images=None,
               free_shipping=None,
               shipping_currency_code=None,
               shipping_domestic=None,
               shipping_international=None,
               options=None,
               moderators=None):
        """
        All parameters are strings except:

        :param expiration_date: `string` (must be formatted UTC datetime)
        :param keywords: `list`
        :param nsfw: `boolean`
        :param images: a `list` of image files
        :param free_shipping: `boolean`
        :param shipping_origin: a 'string' formatted `CountryCode`
        :param shipping_regions: a 'list' of 'string' formatted `CountryCode`s
        :param options: a 'dict' containing options as keys and 'list' as option values.
        :param moderators: a 'list' of 'string' guids (hex encoded).
        """

        profile = Profile().get()
        keychain = KeyChain()
        self.contract = OrderedDict(
            {
                "vendor_offer": {
                    "listing": {
                        "metadata": {
                            "version": "0.1",
                            "expiry": expiration_date + " UTC",
                            "category": metadata_category,
                            "category_sub": "fixed price"
                        },
                        "id": {
                            "guid": keychain.guid.encode("hex"),
                            "pubkeys": {
                                "guid": keychain.guid_signed_pubkey[64:].encode("hex"),
                                "bitcoin": bitcoin.bip32_extract_key(KeyChain().bitcoin_master_pubkey)
                            }
                        },
                        "item": {
                            "title": title,
                            "description": description,
                            "process_time": process_time,
                            "price_per_unit": {},
                            "nsfw": nsfw
                        }
                    }
                }
            }
        )
        if metadata_category == "physical good" and condition is not None:
            self.contract["vendor_offer"]["listing"]["item"]["condition"] = condition
        if currency_code.upper() == "BTC":
            item = self.contract["vendor_offer"]["listing"]["item"]
            item["price_per_unit"]["bitcoin"] = price
        else:
            item = self.contract["vendor_offer"]["listing"]["item"]
            item["price_per_unit"]["fiat"] = {}
            item["price_per_unit"]["fiat"]["price"] = price
            item["price_per_unit"]["fiat"]["currency_code"] = currency_code
        if keywords is not None:
            self.contract["vendor_offer"]["listing"]["item"]["keywords"] = []
            self.contract["vendor_offer"]["listing"]["item"]["keywords"].extend(keywords)
        if category is not None:
            self.contract["vendor_offer"]["listing"]["item"]["category"] = category
        if sku is not None:
            self.contract["vendor_offer"]["listing"]["item"]["sku"] = sku
        if options is not None:
            self.contract["vendor_offer"]["listing"]["item"]["options"] = options
        if metadata_category == "physical good":
            self.contract["vendor_offer"]["listing"]["shipping"] = {}
            shipping = self.contract["vendor_offer"]["listing"]["shipping"]
            shipping["shipping_origin"] = shipping_origin
            if free_shipping is False:
                self.contract["vendor_offer"]["listing"]["shipping"]["free"] = False
                self.contract["vendor_offer"]["listing"]["shipping"]["flat_fee"] = {}
                if shipping_currency_code == "BTC":
                    self.contract["vendor_offer"]["listing"]["shipping"]["flat_fee"]["bitcoin"] = {}
                    self.contract["vendor_offer"]["listing"]["shipping"]["flat_fee"]["bitcoin"][
                        "domestic"] = shipping_domestic
                    self.contract["vendor_offer"]["listing"]["shipping"]["flat_fee"]["bitcoin"][
                        "international"] = shipping_international
                else:
                    shipping = self.contract["vendor_offer"]["listing"]["shipping"]
                    shipping["flat_fee"]["fiat"] = {}
                    shipping["flat_fee"]["fiat"]["price"] = {}
                    shipping["flat_fee"]["fiat"]["price"][
                        "domestic"] = shipping_domestic
                    shipping["flat_fee"]["fiat"]["price"][
                        "international"] = shipping_international
                    shipping["flat_fee"]["fiat"][
                        "currency_code"] = shipping_currency_code
            else:
                self.contract["vendor_offer"]["listing"]["shipping"]["free"] = True
            self.contract["vendor_offer"]["listing"]["shipping"]["shipping_regions"] = []
            for region in shipping_regions:
                shipping = self.contract["vendor_offer"]["listing"]["shipping"]
                shipping["shipping_regions"].append(region)
            listing = self.contract["vendor_offer"]["listing"]
            listing["shipping"]["est_delivery"] = {}
            listing["shipping"]["est_delivery"]["domestic"] = est_delivery_domestic
            listing["shipping"]["est_delivery"][
                "international"] = est_delivery_international
        if profile.HasField("handle"):
            self.contract["vendor_offer"]["listing"]["id"]["blockchain_id"] = profile.handle
        if images is not None:
            self.contract["vendor_offer"]["listing"]["item"]["image_hashes"] = []
            for image in images:
                hash_value = digest(image).encode("hex")
                self.contract["vendor_offer"]["listing"]["item"]["image_hashes"].append(hash_value)
                with open(DATA_FOLDER + "store/media/" + hash_value, 'w') as outfile:
                    outfile.write(image)
                HashMap().insert(digest(image), DATA_FOLDER + "store/media/" + hash_value)
        if terms_conditions is not None or returns is not None:
            self.contract["vendor_offer"]["listing"]["policy"] = {}
            if terms_conditions is not None:
                self.contract["vendor_offer"]["listing"]["policy"]["terms_conditions"] = terms_conditions
            if returns is not None:
                self.contract["vendor_offer"]["listing"]["policy"]["returns"] = returns
        if moderators is not None:
            self.contract["vendor_offer"]["listing"]["moderators"] = []
            for mod in moderators:
                mod_info = ModeratorStore().get_moderator(unhexlify(mod))
                print mod_info
                if mod_info is not None:
                    moderator = {
                        "guid": mod,
                        "blockchain_id": mod_info[6],
                        "pubkeys": {
                            "signing": {
                                "key": mod_info[1][64:].encode("hex"),
                                "signature": mod_info[1][:64].encode("hex")
                            },
                            "encryption": {
                                "key": mod_info[2].encode("hex"),
                                "signature": mod_info[3].encode("hex")
                            },
                            "bitcoin": {
                                "key": mod_info[4].encode("hex"),
                                "signature": mod_info[5].encode("hex")
                            }
                        }
                    }
                    self.contract["vendor_offer"]["listing"]["moderators"].append(moderator)

        listing = json.dumps(self.contract["vendor_offer"]["listing"], indent=4)
        self.contract["vendor_offer"]["signature"] = \
            keychain.signing_key.sign(listing, encoder=nacl.encoding.HexEncoder)[:128]
        self.save()

    def add_purchase_info(self,
                          quantity,
                          ship_to=None,
                          shipping_address=None,
                          city=None,
                          state=None,
                          postal_code=None,
                          country=None,
                          moderator=None,
                          options=None):
        """
        Update the contract with the buyer's purchase information.
        """

        keychain = KeyChain()
        profile = Profile().get()
        order_json = {
            "buyer_order": {
                "order": {
                    "ref_hash": digest(json.dumps(self.contract, indent=4)).encode("hex"),
                    "quantity": quantity,
                    "id": {
                        "guid": keychain.guid.encode("hex"),
                        "pubkeys": {
                            "guid": keychain.guid_signed_pubkey[64:].encode("hex"),
                            "bitcoin": bitcoin.bip32_extract_key(keychain.bitcoin_master_pubkey)
                        }
                    },
                    "payment": {}
                }
            }
        }
        if profile.HasField("handle"):
            order_json["buyer_order"]["order"]["id"]["blockchain_id"] = profile.handle
        if self.contract["vendor_offer"]["listing"]["metadata"]["category"] == "physical good":
            order_json["buyer_order"]["order"]["shipping"] = {}
            order_json["buyer_order"]["order"]["shipping"]["ship_to"] = ship_to
            order_json["buyer_order"]["order"]["shipping"]["address"] = shipping_address
            order_json["buyer_order"]["order"]["shipping"]["city"] = city
            order_json["buyer_order"]["order"]["shipping"]["state"] = state
            order_json["buyer_order"]["order"]["shipping"]["postal_code"] = postal_code
            order_json["buyer_order"]["order"]["shipping"]["country"] = country
        if options is not None:
            order_json["buyer_order"]["order"]["options"] = options
        if moderator:
            chaincode = sha256(str(random.getrandbits(256))).digest().encode("hex")
            order_json["buyer_order"]["order"]["payment"]["chaincode"] = chaincode
            for mod in self.contract["vendor_offer"]["listing"]["moderators"]:
                if mod["guid"] == moderator:
                    order_json["buyer_order"]["order"]["moderator"] = moderator
                    masterkey_m = mod["pubkeys"]["bitcoin"]["key"]
                else:
                    return False

            masterkey_b = bitcoin.bip32_extract_key(keychain.bitcoin_master_pubkey)
            masterkey_v = self.contract["vendor_offer"]["listing"]["id"]["pubkeys"]["bitcoin"]
            buyer_key = derive_childkey(masterkey_b, chaincode)
            vendor_key = derive_childkey(masterkey_v, chaincode)
            moderator_key = derive_childkey(masterkey_m, chaincode)

            redeem_script = '75' + bitcoin.mk_multisig_script([buyer_key, vendor_key, moderator_key], 2)
            order_json["buyer_order"]["order"]["payment"]["redeem_script"] = redeem_script
            if self.testnet:
                payment_address = bitcoin.p2sh_scriptaddr(redeem_script, 196)
            else:
                payment_address = bitcoin.p2sh_scriptaddr(redeem_script)
            order_json["buyer_order"]["order"]["payment"]["address"] = payment_address

        price_json = self.contract["vendor_offer"]["listing"]["item"]["price_per_unit"]
        if "bitcoin" in price_json:
            order_json["buyer_order"]["order"]["payment"]["amount"] = price_json["bitcoin"]
        else:
            currency_code = price_json["fiat"]["currency_code"]
            fiat_price = price_json["fiat"]["price"]
            try:
                request = Request('https://api.bitcoinaverage.com/ticker/' + currency_code.upper() + '/last')
                response = urlopen(request)
                conversion_rate = response.read()
            except URLError:
                return False
            order_json["buyer_order"]["order"]["payment"]["amount"] = float(
                "{0:.8f}".format(float(fiat_price) / float(conversion_rate)))

        self.contract["buyer_order"] = order_json["buyer_order"]
        order = json.dumps(self.contract["buyer_order"]["order"], indent=4)
        self.contract["buyer_order"]["signature"] = \
            keychain.signing_key.sign(order, encoder=nacl.encoding.HexEncoder)[:128]

        return self.contract["buyer_order"]["order"]["payment"]["address"]

    def await_funding(self, websocket_server, libbitcoin_client):
        """
        Saves the contract to the file system and db as an unfunded contract.
        Listens on the libbitcoin server for the multisig address to be funded.
        Deletes the unfunded contract from the file system and db if it goes
        unfunded for more than 10 minutes.
        """

        self.ws = websocket_server
        self.blockchain = libbitcoin_client
        order_id = digest(json.dumps(self.contract, indent=4)).encode("hex")
        file_path = DATA_FOLDER + "store/listings/in progress/" + order_id + ".json"
        with open(file_path, 'w') as outfile:
            outfile.write(json.dumps(self.contract, indent=4))
        payment_address = self.contract["buyer_order"]["order"]["payment"]["address"]
        self.timeout = reactor.callLater(600, self._delete_unfunded)
        self.blockchain.subscribe_address(payment_address, notification_cb=self._on_tx_received)

    def _delete_unfunded(self):
        """
        The user failed to fund the contract in the 10 minute window. Remove it from
        the file system and db.
        """
        order_id = digest(json.dumps(self.contract, indent=4)).encode("hex")
        file_path = DATA_FOLDER + "store/listings/in progress/" + order_id + ".json"
        if os.path.exists(file_path):
            os.remove(file_path)

    def _on_tx_received(self, address_version, address_hash, height, block_hash, tx):
        """
        Fire when the libbitcoin server tells us we received a payment to this funding address.
        While unlikely, a user may send multiple transactions to the funding address reach the
        funding level. We need to keep a running balance and increment it when a new transaction
        is received. If the contract is fully funded, we push a notification to the websockets.
        """
        # decode the transaction
        transaction = bitcoin.deserialize(tx.encode("hex"))

        # get the amount (in satoshi) the user is expected to pay
        amount_to_pay = int(float(self.contract["buyer_order"]["order"]["payment"]["amount"]) * 100000000)
        if tx not in self.received_txs:  # make sure we aren't parsing the same tx twice.
            output_script = 'a914' + digest(unhexlify(
                self.contract["buyer_order"]["order"]["payment"]["redeem_script"])).encode("hex") + '87'
            for output in transaction["outs"]:
                if output["script"] == output_script:
                    self.amount_funded += output["value"]
                    if tx not in self.received_txs:
                        self.received_txs.append(tx)
            if self.amount_funded >= amount_to_pay:  # if fully funded
                self.timeout.cancel()
                self.blockchain.unsubscribe_address(
                    self.contract["buyer_order"]["order"]["payment"]["address"], self._on_tx_received)
                message_json = {
                    "payment_received": {
                        "address": self.contract["buyer_order"]["order"]["payment"]["address"],
                        "order_id": digest(json.dumps(self.contract, indent=4)).encode("hex")
                        }
                }
                # push funding message over websockets
                self.ws.push(json.dumps(message_json, indent=4))

                # update the db

    def get_contract_id(self):
        contract = json.dumps(self.contract, indent=4)
        return digest(contract)

    def delete(self, delete_images=True):
        """
        Deletes the contract json from the OpenBazaar directory as well as the listing
        metadata from the db and all the related images in the file system.
        """

        # build the file_name from the contract
        file_name = str(self.contract["vendor_offer"]["listing"]["item"]["title"][:100])
        file_name = re.sub(r"[^\w\s]", '', file_name)
        file_name = re.sub(r"\s+", '_', file_name)
        file_path = DATA_FOLDER + "store/listings/contracts/" + file_name + ".json"

        h = HashMap()

        # maybe delete the images from disk
        if "image_hashes" in self.contract["vendor_offer"]["listing"]["item"] and delete_images:
            for image_hash in self.contract["vendor_offer"]["listing"]["item"]["image_hashes"]:
                # delete from disk
                image_path = h.get_file(unhexlify(image_hash))
                if os.path.exists(image_path):
                    os.remove(image_path)
                # remove pointer to the image from the HashMap
                h.delete(unhexlify(image_hash))

        # delete the contract from disk
        if os.path.exists(file_path):
            os.remove(file_path)

        # delete the listing metadata from the db
        contract_hash = digest(json.dumps(self.contract, indent=4))
        ListingsStore().delete_listing(contract_hash)

        # remove the pointer to the contract from the HashMap
        h.delete(contract_hash)

    def save(self):
        """
        Saves the json contract into the OpenBazaar/store/listings/contracts/ directory.
        It uses the title as the file name so it's easy on human eyes. A mapping of the
        hash of the contract and file path is stored in the database so we can retrieve
        the contract with only its hash.

        Additionally, the contract metadata (sent in response to the GET_LISTINGS query)
        is saved in the db for fast access.
        """
        # get the contract title to use as the file name and format it
        file_name = str(self.contract["vendor_offer"]["listing"]["item"]["title"][:100])
        file_name = re.sub(r"[^\w\s]", '', file_name)
        file_name = re.sub(r"\s+", '_', file_name)

        # save the json contract to the file system
        file_path = DATA_FOLDER + "store/listings/contracts/" + file_name + ".json"
        with open(file_path, 'w') as outfile:
            outfile.write(json.dumps(self.contract, indent=4))

        # Create a `ListingMetadata` protobuf object using data from the full contract
        listings = Listings()
        data = listings.ListingMetadata()
        data.contract_hash = digest(json.dumps(self.contract, indent=4))
        vendor_item = self.contract["vendor_offer"]["listing"]["item"]
        data.title = vendor_item["title"]
        if "image_hashes" in vendor_item:
            data.thumbnail_hash = unhexlify(vendor_item["image_hashes"][0])
        if "category" in vendor_item:
            data.category = vendor_item["category"]
        if "bitcoin" not in vendor_item["price_per_unit"]:
            data.price = float(vendor_item["price_per_unit"]["fiat"]["price"])
            data.currency_code = vendor_item["price_per_unit"]["fiat"][
                "currency_code"]
        else:
            data.price = float(vendor_item["price_per_unit"]["bitcoin"])
            data.currency_code = "BTC"
        data.nsfw = vendor_item["nsfw"]
        if "shipping" not in self.contract["vendor_offer"]["listing"]:
            data.origin = CountryCode.Value("NA")
        else:
            data.origin = CountryCode.Value(
                self.contract["vendor_offer"]["listing"]["shipping"]["shipping_origin"].upper())
            for region in self.contract["vendor_offer"]["listing"]["shipping"]["shipping_regions"]:
                data.ships_to.append(CountryCode.Value(region.upper()))

        # save the mapping of the contract file path and contract hash in the database
        HashMap().insert(data.contract_hash, file_path)

        # save the `ListingMetadata` protobuf to the database as well
        ListingsStore().add_listing(data)
