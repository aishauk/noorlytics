"""
Sample Python file with common refactoring opportunities.
Used for testing the refactor command with various code quality issues.
"""


def process_data(data):
    """Process data with potential refactoring opportunities."""
    result = []
    for i in range(len(data)):
        x = data[i]
        if x > 10:
            result.append(x * 2)
        elif x > 5:
            result.append(x + 5)
        else:
            result.append(x)
    return result


def calculate_discount(price, customer_type):
    """Calculate discount with magic numbers and unclear logic."""
    if customer_type == 'premium':
        discount = price * 0.2
    elif customer_type == 'regular':
        discount = price * 0.1
    elif customer_type == 'new':
        discount = price * 0.05
    else:
        discount = 0
    
    final_price = price - discount
    return final_price


class DataProcessor:
    """Class with multiple code quality issues."""
    
    def __init__(self):
        self.data = []
        self.processed_data = []
        self.error_count = 0
    
    def add_item(self, item):
        """Add item with poor naming."""
        if item != None:
            self.data.append(item)
        else:
            self.error_count = self.error_count + 1
    
    def process_all(self):
        """Process all items with nested loops and complexity."""
        for idx in range(len(self.data)):
            item = self.data[idx]
            temp = item * 2
            if temp > 100:
                temp = 100
            if temp < 0:
                temp = 0
            self.processed_data.append(temp)
    
    def get_stats(self):
        """Get statistics with repeated logic."""
        total = 0
        count = 0
        for i in range(len(self.processed_data)):
            total = total + self.processed_data[i]
            count = count + 1
        
        if count > 0:
            avg = total / count
        else:
            avg = 0
        
        return {'total': total, 'count': count, 'average': avg}


def validate_email(email):
    """Email validation with poor pattern matching."""
    if '@' in email:
        parts = email.split('@')
        if len(parts) == 2:
            if '.' in parts[1]:
                return True
    return False


def format_output(name, age, city):
    """String formatting with concatenation instead of f-strings."""
    output = "Name: " + name + ", Age: " + str(age) + ", City: " + city
    return output


if __name__ == '__main__':
    # Test the functions
    test_data = [3, 8, 12, 15, 7]
    print("Process data:", process_data(test_data))
    
    print("Calculate discount:", calculate_discount(100, 'premium'))
    
    processor = DataProcessor()
    for val in test_data:
        processor.add_item(val)
    processor.process_all()
    print("Stats:", processor.get_stats())
    
    print("Valid email:", validate_email("test@example.com"))
    print("Format output:", format_output("Alice", 30, "New York"))
