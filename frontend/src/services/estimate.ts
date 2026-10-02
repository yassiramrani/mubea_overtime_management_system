// Mirror the API's two-decimal, half-even rounding without floating-point ties.
export function estimatedTotal(hours: string, rate: string): string | null {
  const decimal = /^(?:\d+(?:\.\d{0,2})?|\.\d{1,2})$/
  if (!decimal.test(hours) || !decimal.test(rate)) return null
  const hundredths = (value: string) => {
    const [whole, fraction = ''] = value.split('.')
    return BigInt(whole || '0') * 100n + BigInt(fraction.padEnd(2, '0'))
  }
  const product = hundredths(hours) * hundredths(rate)
  let cents = product / 100n
  const remainder = product % 100n
  if (remainder > 50n || (remainder === 50n && cents % 2n === 1n)) cents += 1n
  return `${cents / 100n}.${String(cents % 100n).padStart(2, '0')}`
}
