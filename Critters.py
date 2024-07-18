import smartpy as sp

class GameContract(sp.Contract):
    def __init__(self, owner):
        self.init(
            games = sp.big_map(tkey=sp.TNat, tvalue=sp.TRecord(
                participants = sp.TMap(sp.TAddress, sp.TMutez),
                totalAmount = sp.TMutez,
                started = sp.TBool,
                ended = sp.TBool,
                maxParticipants = sp.TNat,
                deadline = sp.TTimestamp
            )),
            gameCounter = 0,
            feePercentage = sp.nat(2),  # Default 2% fee
            numWinners = 3,
            winnerDistribution = sp.list([sp.nat(50), sp.nat(30), sp.nat(20)]),  # Default distribution
            owner = owner,
            admins = sp.set([owner]),
            totalFee = sp.mutez(0)
        )

    @sp.entry_point
    def create_game(self, params):
        sp.verify(self.is_admin(sp.sender), message="Only admin can create a game")
        self.data.games[self.data.gameCounter] = sp.record(
            participants = sp.map(tkey=sp.TAddress, tvalue=sp.TMutez),
            totalAmount = sp.mutez(0),
            started = False,
            ended = False,
            maxParticipants = params.maxParticipants,
            deadline = sp.now.add_seconds(params.deadline)
        )
        self.data.gameCounter += 1

    @sp.entry_point
    def join_game(self, params):
        game = self.data.games[params.game_id]
        sp.verify(~game.started, message="Game already started")
        sp.verify(~game.ended, message="Game already ended")
        sp.verify(sp.now <= game.deadline, message="Game deadline has passed")
        sp.verify(sp.len(game.participants) < game.maxParticipants, message="Max participants reached")
        game.participants[sp.sender] = params.amount
        game.totalAmount += params.amount

        # Automatically start the game if max participants are reached
        if sp.len(game.participants) == game.maxParticipants:
            game.started = True

    @sp.entry_point
    def start_game(self, params):
        sp.verify(self.is_admin(sp.sender), message="Only admin can start the game")
        self.data.games[params.game_id].started = True

    @sp.entry_point
    def end_game(self, params):
        sp.verify(self.is_admin(sp.sender), message="Only admin can end the game")
        game = self.data.games[params.game_id]
        sp.verify(game.started, message="Game not started")
        sp.verify(~game.ended, message="Game already ended")
        
        winners = params.winners
        sp.verify(sp.len(winners) == self.data.numWinners, message="Number of winners does not match the expected number")
        
        totalAmount = game.totalAmount
        fee = sp.split_tokens(totalAmount, self.data.feePercentage, 100)
        prize = totalAmount - fee
        
        # Add fee to the total fee
        self.data.totalFee += fee

        # Distribute the prize to winners based on the distribution percentages
        for i in sp.range(0, self.data.numWinners):
            prize_share = sp.split_tokens(prize, self.data.winnerDistribution[i], 100)
            sp.send(winners[i], prize_share)
        
        game.ended = True

    @sp.entry_point
    def cancel_game(self, params):
        sp.verify(self.is_admin(sp.sender), message="Only admin can cancel the game")
        game = self.data.games[params.game_id]
        sp.verify(~game.ended, message="Game already ended")
        
        for participant in game.participants.keys():
            sp.send(participant, game.participants[participant])
        
        game.ended = True

    @sp.entry_point
    def set_max_participants(self, params):
        sp.verify(self.is_admin(sp.sender), message="Only admin can set the max participants")
        game = self.data.games[params.game_id]
        sp.verify(~game.started, message="Cannot set max participants after game has started")
        game.maxParticipants = params.maxParticipants

    @sp.entry_point
    def set_winner_distribution(self, params):
        sp.verify(self.is_admin(sp.sender), message="Only admin can set the winner distribution")
        sp.verify(sp.len(params.winnerDistribution) == self.data.numWinners, message="Distribution length does not match the number of winners")
        total_percentage = sp.sum(params.winnerDistribution)
        sp.verify(total_percentage == 100, message="Total distribution percentage must equal 100")
        self.data.winnerDistribution = params.winnerDistribution

    @sp.entry_point
    def set_fee_percentage(self, params):
        sp.verify(self.is_admin(sp.sender), message="Only admin can set the fee percentage")
        sp.verify(params.feePercentage <= 100, message="Fee percentage must be less than or equal to 100")
        self.data.feePercentage = params.feePercentage

    @sp.entry_point
    def check_deadlines(self):
        for game_id in self.data.games.keys():
            game = self.data.games[game_id]
            if not game.started and sp.now > game.deadline:
                game.started = True

    @sp.entry_point
    def add_admin(self, params):
        sp.verify(sp.sender == self.data.owner, message="Only owner can add an admin")
        self.data.admins.add(params.admin)

    @sp.entry_point
    def remove_admin(self, params):
        sp.verify(sp.sender == self.data.owner, message="Only owner can remove an admin")
        sp.verify(params.admin != self.data.owner, message="Owner cannot be removed as admin")
        self.data.admins.remove(params.admin)

    @sp.entry_point
    def transfer_ownership(self, params):
        sp.verify(sp.sender == self.data.owner, message="Only owner can transfer ownership")
        self.data.owner = params.new_owner
        self.data.admins.remove(sp.sender)
        self.data.admins.add(params.new_owner)

    @sp.entry_point
    def withdraw_fees(self, params):
        sp.verify(sp.sender == self.data.owner, message="Only owner can withdraw fees")
        sp.send(self.data.owner, self.data.totalFee)
        self.data.totalFee = sp.mutez(0)

    def is_admin(self, address):
        return self.data.admins.contains(address)

@sp.add_test(name = "Game Contract Test")
def test():
    scenario = sp.test_scenario()
    owner = sp.test_account("Owner")
    admin1 = sp.test_account("Admin1")
    admin2 = sp.test_account("Admin2")
    alice = sp.test_account("Alice")
    bob = sp.test_account("Bob")
    charlie = sp.test_account("Charlie")
    dave = sp.test_account("Dave")

    game_contract = GameContract(owner.address)
    scenario += game_contract

    scenario.h1("Owner adds admins")
    scenario += game_contract.add_admin(params=sp.record(admin=admin1.address)).run(sender=owner)
    scenario += game_contract.add_admin(params=sp.record(admin=admin2.address)).run(sender=owner)

    scenario.h1("Create a new game")
    scenario += game_contract.create_game(params=sp.record(maxParticipants=3, deadline=60)).run(sender=admin1)

    scenario.h1("Join the game")
    scenario += game_contract.join_game(params=sp.record(game_id=0, amount=sp.mutez(1000))).run(sender=alice)
    scenario += game_contract.join_game(params=sp.record(game_id=0, amount=sp.mutez(1000))).run(sender=bob)
    scenario += game_contract.join_game(params=sp.record(game_id=0, amount=sp.mutez(1000))).run(sender=charlie)

    scenario.h1("Set winner distribution")
    scenario += game_contract.set_winner_distribution(params=sp.record(winnerDistribution=[50, 30, 20])).run(sender=admin1)

    scenario.h1("Set fee percentage")
    scenario += game_contract.set_fee_percentage(params=sp.record(feePercentage=5)).run(sender=admin1)

    scenario.h1("Start the game")
    scenario += game_contract.start_game(params=sp.record(game_id=0)).run(sender=admin1)

    scenario.h1("End the game and distribute winnings")
    scenario += game_contract.end_game(params=sp.record(game_id=0, winners=[alice.address, bob.address, charlie.address])).run(sender=admin1)

    scenario.h1("Create and cancel a game")
    scenario += game_contract.create_game(params=sp.record(maxParticipants=3, deadline=60)).run(sender=admin1)
    scenario += game_contract.join_game(params=sp.record(game_id=1, amount=sp.mutez(1000))).run(sender=alice)
    scenario += game_contract.cancel_game(params=sp.record(game_id=1)).run(sender=admin1)

    scenario.h1("Create a game and update max participants")
    scenario += game_contract.create_game(params=sp.record(maxParticipants=2, deadline=60)).run(sender=admin1)
    scenario += game_contract.set_max_participants(params=sp.record(game_id=2, maxParticipants=3)).run(sender=admin1)
    scenario += game_contract.join_game(params=sp.record(game_id=2, amount=sp.mutez(1000))).run(sender=alice)
    scenario += game_contract.join_game(params=sp.record(game_id=2, amount=sp.mutez(1000))).run(sender=bob)
    scenario += game_contract.join_game(params=sp.record(game_id=2, amount=sp.mutez(1000))).run(sender=charlie)

    scenario.h1("Check deadlines")
    scenario += game_contract.check_deadlines().run(sender=admin1, now=sp.timestamp(70))

    scenario.h1("Owner removes an admin")
    scenario += game_contract.remove_admin(params=sp.record(admin=admin2.address)).run(sender=owner)

    scenario.h1("Owner transfers ownership")
    scenario += game_contract.transfer_ownership(params=sp.record(new_owner=admin1.address)).run(sender=owner)

    scenario.h1("New owner adds a new admin")
    scenario += game_contract.add_admin(params=sp.record(admin=admin2.address)).run(sender=admin1)

    scenario.h1("Owner withdraws accumulated fees")
    scenario += game_contract.withdraw_fees(params=sp.unit).run(sender=admin1)

