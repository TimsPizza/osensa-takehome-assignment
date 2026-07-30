export const MQTT_URL_STORAGE_KEY = 'osensa.mqtt.websocket-url';
export const MQTT_USERNAME_SESSION_KEY = 'osensa.mqtt.username';
export const MQTT_PASSWORD_SESSION_KEY = 'osensa.mqtt.password';

export interface BrokerCredentials {
	username: string;
	password: string;
}

export interface BrokerConnectionSettings {
	url: string;
	credentials?: BrokerCredentials;
}

export interface BrowserLocation {
	protocol: string;
	hostname: string;
}

export interface BrowserStorage {
	getItem(key: string): string | null;
	setItem(key: string, value: string): void;
	removeItem(key: string): void;
}

export function resolveMqttUrl(location: BrowserLocation, configuredUrl?: string): string {
	const explicitUrl = configuredUrl?.trim();
	if (explicitUrl) {
		return explicitUrl;
	}

	const websocketProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
	const localPort =
		location.hostname === 'localhost' || location.hostname === '127.0.0.1' ? ':9001' : '';
	return `${websocketProtocol}//${location.hostname}${localPort}/mqtt`;
}

export function normalizeMqttUrl(value: string, pageProtocol?: string): string {
	const candidate = value.trim();
	if (!candidate) {
		throw new Error('Enter a Broker WebSocket URL.');
	}

	let url: URL;
	try {
		url = new URL(candidate);
	} catch {
		throw new Error('Enter a complete URL, for example wss://broker.example.com/mqtt.');
	}

	if (url.protocol !== 'ws:' && url.protocol !== 'wss:') {
		throw new Error('The Broker URL must use ws:// or wss://.');
	}
	if (!url.hostname) {
		throw new Error('The Broker URL must include a hostname.');
	}
	if (pageProtocol === 'https:' && url.protocol !== 'wss:') {
		throw new Error('An HTTPS page requires a secure wss:// Broker URL.');
	}
	if (url.hash) {
		throw new Error('Remove the #fragment from the Broker URL.');
	}

	return url.href;
}

export function readStoredMqttUrl(
	storage: BrowserStorage,
	pageProtocol?: string
): string | undefined {
	try {
		const storedUrl = storage.getItem(MQTT_URL_STORAGE_KEY);
		return storedUrl ? normalizeMqttUrl(storedUrl, pageProtocol) : undefined;
	} catch {
		return undefined;
	}
}

export function storeMqttUrl(
	storage: BrowserStorage,
	value: string,
	pageProtocol?: string
): string {
	const normalizedUrl = normalizeMqttUrl(value, pageProtocol);
	storage.setItem(MQTT_URL_STORAGE_KEY, normalizedUrl);
	return normalizedUrl;
}

export function clearStoredMqttUrl(storage: BrowserStorage): void {
	storage.removeItem(MQTT_URL_STORAGE_KEY);
}

export function normalizeMqttCredentials(
	usernameValue: string,
	password: string
): BrokerCredentials | undefined {
	const username = usernameValue.trim();
	if (!username && !password) {
		return undefined;
	}
	if (!username || !password) {
		throw new Error('Enter both the Broker username and password.');
	}
	if (username.length > 128) {
		throw new Error('The Broker username must be 128 characters or fewer.');
	}
	if (password.length > 512) {
		throw new Error('The Broker password must be 512 characters or fewer.');
	}
	return { username, password };
}

export function readSessionMqttCredentials(storage: BrowserStorage): BrokerCredentials | undefined {
	try {
		return normalizeMqttCredentials(
			storage.getItem(MQTT_USERNAME_SESSION_KEY) ?? '',
			storage.getItem(MQTT_PASSWORD_SESSION_KEY) ?? ''
		);
	} catch {
		return undefined;
	}
}

export function storeSessionMqttCredentials(
	storage: BrowserStorage,
	credentials: BrokerCredentials | undefined
): void {
	if (!credentials) {
		clearSessionMqttCredentials(storage);
		return;
	}

	const normalized = normalizeMqttCredentials(credentials.username, credentials.password);
	if (!normalized) {
		clearSessionMqttCredentials(storage);
		return;
	}
	storage.setItem(MQTT_USERNAME_SESSION_KEY, normalized.username);
	storage.setItem(MQTT_PASSWORD_SESSION_KEY, normalized.password);
}

export function clearSessionMqttCredentials(storage: BrowserStorage): void {
	storage.removeItem(MQTT_USERNAME_SESSION_KEY);
	storage.removeItem(MQTT_PASSWORD_SESSION_KEY);
}
