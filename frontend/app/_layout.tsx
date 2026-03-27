import { useEffect, useState } from 'react';
import { Stack, useRouter, useSegments } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { View, ActivityIndicator } from 'react-native';
import { useFonts } from 'expo-font';

export default function RootLayout() {
  const router   = useRouter();
  const segments = useSegments();
  const [ready, setReady]   = useState(false);
  const [role,  setRole]    = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const stored = await AsyncStorage.getItem('role');
      setRole(stored);
      setReady(true);
    })();
  }, []);

  useEffect(() => {
    if (!ready) return;
    const inAuth = segments[0] === 'login';
    if (!role && !inAuth) {
      router.replace('/login');
    } else if (role && inAuth) {
      router.replace('/gallery');
    }
  }, [ready, role, segments]);

  if (!ready) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#FFF0F3' }}>
        <ActivityIndicator color="#FFC0CB" size="large" />
      </View>
    );
  }

  return (
    <Stack screenOptions={{ headerShown: false, animation: 'fade' }}>
      <Stack.Screen name="login"   options={{ gestureEnabled: false }} />
      <Stack.Screen name="gallery" options={{ gestureEnabled: false }} />
      <Stack.Screen name="manage"  options={{ gestureEnabled: false }} />
    </Stack>
  );
}
