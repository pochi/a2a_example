import asyncio
import argparse
from cost_estimator_agent.cost_estimator_agent import AWSCostEstimatorAgent

def test_regular(architecture: str = "One EC2 t3.micro instance running 8 hours per day", verbose: bool=True) -> bool:
    if verbose:
        print('📆Testing cost estimation')
    agent = AWSCostEstimatorAgent()

    try:
        result = agent.estimate_costs(architecture)
        if verbose:
            print(f"📊Regular response length: {len(result)} characters")
            print(f"Result preview: {result[:150]}...")
        return len(result) > 0
    except Exception as e:
        if verbose:
            print(f"✖️ Test failed: {e}")
        return False

def parse_argument():
    parser = argparse.ArgumentParser(description="Sample Agent: Calculate AWS Cost")

    parser.add_argument(
        '--architecture', 
        type=str, 
        default="One EC2 t3.micro instance running 8 hours per day",
        help='Architecture description to test (default: "One EC2 t3.micro instance running 24/7")'
    )
    
    parser.add_argument(
        '--tests',
        nargs='+',
        choices=['regular', 'streaming', 'debug'],
        default=['regular'],
        help='Which tests to run (default: regular)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        default=True,
        help='Enable verbose output (default: True)'
    )
    
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Disable verbose output'
    )
    
    return parser.parse_args()

async def main() -> None:
    args = parse_argument()
    verbose = args.verbose and not args.quiet

    print('🤖 testing aws cost agent')

    results = {}

    if verbose:
        print(f"Architecture: {args.architecture}")
        print(f"Tests to run: {', '.join(args.tests)}")

    if 'regular' in args.tests:
        results['regular'] = test_regular(args.architecture, verbose)
    
    if 'streaming' in args.tests:
        results['streaming'] = await test_streaming(args.architecture, verbose)

    if verbose:
        print("\n📈 Test Results:")
        for name, result in results.items():
            status = '✅ PASS' if result else '✖️ FAIL'
            print(f"  {name.capitalize()} implementation: {status}")

if __name__ == '__main__':
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)