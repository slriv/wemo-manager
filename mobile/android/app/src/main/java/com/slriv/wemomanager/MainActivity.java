package com.slriv.wemomanager;

import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkRequest;
import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    private ConnectivityManager connectivity;
    private ConnectivityManager.NetworkCallback callback;
    private Network bound;

    // Android routes off Wi-Fi when it sees no internet, stranding the WeMo access point.
    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        connectivity = getSystemService(ConnectivityManager.class);
        callback =
            new ConnectivityManager.NetworkCallback() {
                @Override
                public void onAvailable(Network network) {
                    bound = network;
                    connectivity.bindProcessToNetwork(network);
                }

                // A Wi-Fi switch reports the new network before losing the old.
                @Override
                public void onLost(Network network) {
                    if (network.equals(bound)) {
                        bound = null;
                        connectivity.bindProcessToNetwork(null);
                    }
                }
            };
        connectivity.registerNetworkCallback(
            new NetworkRequest.Builder()
                .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
                .removeCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                .build(),
            callback
        );
    }

    @Override
    public void onDestroy() {
        connectivity.unregisterNetworkCallback(callback);
        connectivity.bindProcessToNetwork(null);
        super.onDestroy();
    }
}
