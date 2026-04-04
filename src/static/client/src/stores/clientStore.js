import {defineStore} from "pinia";
import {onMounted, reactive, ref} from "vue";
import {v4} from "uuid"
import dayjs from "dayjs";
import {axiosGet, axiosPost} from "@/utilities/request.js";


export const clientStore = defineStore('clientStore',  {
	state: () => ({
		serverInformation: {},
		notifications: [],
		configurations: [],
		managedConfigurations: [],
		clientProfile: {
			Email: "",
			SignInMethod: "",
			Profile: {}
		}
	}),
	actions: {
		newNotification(content, status){
			this.notifications.push({
				id: v4().toString(),
				status: status,
				content: content,
				time: dayjs(),
				show: true
			})
		},
		async getClientProfile(){
			const data = await axiosGet('/api/settings/getClientProfile')
			if (data){
				this.clientProfile = data.data
			}else{
				this.newNotification("Failed to fetch client profile", "danger")
			}
		},
		async getConfigurations(){
			const data = await axiosGet("/api/configurations")
			if (data){
				this.configurations = data.data
			}else{
				this.newNotification("Failed to fetch configurations", "danger")
			}
		},
		async getManagedConfigurations(){
			const data = await axiosGet("/api/managedConfigurations")
			if (data){
				this.managedConfigurations = data.data
			}else{
				this.newNotification("Failed to fetch managed configurations", "danger")
			}
		},
		async getManagedConfigPeers(configName){
			const data = await axiosGet(`/api/managedConfigurations/${configName}/peers`)
			if (data){
				return data.data
			}else{
				this.newNotification("Failed to fetch peers", "danger")
				return null
			}
		},
		async addManagedPeer(configName, peerData){
			const data = await axiosPost(`/api/managedConfigurations/${configName}/addPeers`, peerData)
			if (data && data.status){
				this.newNotification("Peer added successfully", "success")
				return data.data
			}else{
				this.newNotification(data?.message || "Failed to add peer", "danger")
				return null
			}
		},
		async deleteManagedPeers(configName, peers){
			const data = await axiosPost(`/api/managedConfigurations/${configName}/deletePeers`, {peers})
			if (data && data.status){
				this.newNotification("Peer(s) deleted", "success")
				return true
			}else{
				this.newNotification(data?.message || "Failed to delete peer(s)", "danger")
				return false
			}
		},
		async restrictManagedPeers(configName, peers){
			const data = await axiosPost(`/api/managedConfigurations/${configName}/restrictPeers`, {peers})
			if (data && data.status){
				this.newNotification("Peer(s) restricted", "success")
				return true
			}else{
				this.newNotification(data?.message || "Failed to restrict peer(s)", "danger")
				return false
			}
		},
		async allowManagedPeers(configName, peers){
			const data = await axiosPost(`/api/managedConfigurations/${configName}/allowAccessPeers`, {peers})
			if (data && data.status){
				this.newNotification("Peer(s) access restored", "success")
				return true
			}else{
				this.newNotification(data?.message || "Failed to allow peer(s)", "danger")
				return false
			}
		},
		async downloadManagedPeer(configName, peerId){
			const data = await axiosGet(`/api/managedConfigurations/${configName}/downloadPeer?id=${encodeURIComponent(peerId)}`)
			if (data && data.status){
				return data.data
			}else{
				this.newNotification("Failed to download peer config", "danger")
				return null
			}
		}
	}
})