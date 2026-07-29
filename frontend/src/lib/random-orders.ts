import type { OrderRequested } from '$lib/generated/contracts';
import type { TableId } from '$lib/order-state';

const FOOD_NAMES = [
	'Margherita pizza',
	'Chicken sandwich',
	'Tomato soup',
	'Beef tacos',
	'Mushroom pasta',
	'Caesar salad',
	'Fish and chips',
	'Vegetable curry',
	'Cheeseburger',
	'Chocolate cake',
	'Grilled salmon',
	'Avocado toast'
] as const;

type RandomOrder = OrderRequested & { tableId: TableId };

interface RandomOrderOptions {
	count?: number;
	random?: () => number;
	createId?: () => string;
}

export function createRandomOrders(
	tableId: TableId,
	{
		count = 10,
		random = Math.random,
		createId = () => crypto.randomUUID()
	}: RandomOrderOptions = {}
): RandomOrder[] {
	if (!Number.isInteger(count) || count < 1 || count > 500) {
		throw new RangeError('count must be an integer between 1 and 500');
	}

	return Array.from({ length: count }, () => {
		const foodIndex = Math.min(Math.floor(random() * FOOD_NAMES.length), FOOD_NAMES.length - 1);
		return {
			schemaVersion: 1,
			orderId: createId(),
			tableId,
			foodName: FOOD_NAMES[foodIndex]
		};
	});
}
