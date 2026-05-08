// Centralized API wrappers for the whole dashboard.
//
// Error policy:
//   - 401            → toast + redirect to /signin (real auth failure)
//   - any other 4xx/5xx → toast with the server's error message; user stays on page
//   - network/fetch reject → toast "Request failed: ..."
//
// A 5xx must NOT log the user out — masking a backend bug as an expired
// session was a real incident, so handleResponse below treats only 401
// as auth and routes everything else through the message store.

import {DashboardConfigurationStore} from "@/stores/DashboardConfigurationStore.js";
import router from "@/router/router.js";
const getHeaders = () => {
	let headers = {
		"Content-Type": "application/json"
	}
	const store = DashboardConfigurationStore();
	const crossServer = store.getActiveCrossServer();
	if (crossServer){
		headers['wg-dashboard-apikey'] = crossServer.apiKey
        if (crossServer.headers){
            for (let header of Object.values(crossServer.headers)){
                if (header.key && header.value && !Object.keys(headers).includes(header.key)){
                    headers[header.key] = header.value
                }
            }
        }
	}


	return headers
}

export const getUrl = (url) => {
	const store = DashboardConfigurationStore();
	const apiKey = store.getActiveCrossServer();
	if (apiKey){
		return `${apiKey.host}${url}`
	}
	return import.meta.env.MODE === 'development' ? url
		: `${window.location.protocol}//${(window.location.host + window.location.pathname + url).replace(/\/\//g, '/')}`
}

const extractErrorMessage = async (response) => {
	try {
		const body = await response.clone().json()
		if (body && (body.message || body.error)) {
			return body.message || body.error
		}
	} catch (e) { /* not JSON, fall through */ }
	try {
		const text = await response.clone().text()
		if (text) return text.length > 300 ? text.slice(0, 300) + '…' : text
	} catch (e) { /* ignore */ }
	return response.statusText || `HTTP ${response.status}`
}

const handleResponse = async (response, callback) => {
	const store = DashboardConfigurationStore()
	if (response.ok) {
		const data = await response.json()
		if (callback) callback(data)
		return
	}
	if (response.status === 401) {
		store.newMessage("WGDashboard", "Sign in session ended, please sign in again", "warning")
		router.push({path: '/signin'})
		return
	}
	const detail = await extractErrorMessage(response)
	store.newMessage(
		"Server",
		`Error ${response.status}: ${detail}`,
		"danger"
	)
}

const handleNetworkError = (err) => {
	console.error("Network/fetch error:", err)
	const store = DashboardConfigurationStore()
	store.newMessage(
		"Network",
		`Request failed: ${err && err.message ? err.message : err}`,
		"danger"
	)
}

export const fetchGet = async (url, params=undefined, callback=undefined) => {
	const urlSearchParams = new URLSearchParams(params)
	try {
		const response = await fetch(`${getUrl(url)}?${urlSearchParams.toString()}`, {
			headers: getHeaders()
		})
		await handleResponse(response, callback)
	} catch (err) {
		handleNetworkError(err)
	}
}

export const fetchPost = async (url, body, callback) => {
	try {
		const response = await fetch(`${getUrl(url)}`, {
			headers: getHeaders(),
			method: "POST",
			body: JSON.stringify(body)
		})
		await handleResponse(response, callback)
	} catch (err) {
		handleNetworkError(err)
	}
}
