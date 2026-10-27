import sys
sys.path.insert(0, '.')
from utils.text_analyzer import check_patterns

text = 'Urgent hiring! Work from home data entry job. Earn Rs 45000 per month. No experience needed. Only 3 seats left. Pay Rs 999 registration fee before joining. Daily payment via UPI. Work timing 24/7 you can work anytime. hr.nexgen2024@gmail.com'

flags, score = check_patterns(text)
print('Score:', score)
print('Flags found:')
for f in flags:
    print(' ', f)