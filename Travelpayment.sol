// TravelPayment.sol
pragma solidity ^0.8.0;

contract TravelPayment {
    address public owner;
    mapping(address => uint256) public payments;
    
    event PaymentReceived(address indexed payer, uint256 amount);
    
    constructor() {
        owner = msg.sender;
    }
    
    function makePayment() public payable {
        require(msg.value > 0, "Payment amount must be greater than 0");
        payments[msg.sender] += msg.value;
        emit PaymentReceived(msg.sender, msg.value);
    }
    
    function withdrawFunds() public {
        require(msg.sender == owner, "Only owner can withdraw");
        payable(owner).transfer(address(this).balance);
    }
}
