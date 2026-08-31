import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Animated,
  BackHandler,
  Image,
  KeyboardAvoidingView,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import * as SplashScreen from 'expo-splash-screen';
import { Ionicons } from '@expo/vector-icons';
import { StatusBar } from 'expo-status-bar';
import {
  DrawerContentScrollView,
  DrawerItem,
  createDrawerNavigator,
} from '@react-navigation/drawer';
import {
  DefaultTheme,
  NavigationContainer,
} from '@react-navigation/native';
import { SafeAreaProvider, useSafeAreaInsets } from 'react-native-safe-area-context';
import { WebView } from 'react-native-webview';

const colors = {
  navy: '#102B4E',
  blue: '#31518C',
  gold: '#C7943E',
  ink: '#18324D',
  muted: '#718096',
  canvas: '#F5F7FA',
  danger: '#A34843',
  white: '#FFFFFF',
  border: '#E3E8EF',
};

const WEB_APP_URL = (
  process.env.EXPO_PUBLIC_WEB_APP_URL || 'http://127.0.0.1:8000'
).replace(/\/$/, '');

const AUTH_PATH = '/accounts/login/';
const ACCOUNT_DELETE_PATH = '/accounts/delete/';
const PRIVACY_PATH = '/privacy/';
const TERMS_PATH = '/terms/';
const HOME_PATH = '/';
const EMPLOYEE_WORKSPACE_PATH = '/team/';
const EMPLOYEE_PROJECTS_PATH = '/team/projects/';
const EMPLOYEE_PROFILE_PATH = '/team/profile/';
const CLIENT_WORKSPACE_PATH = '/portal/';
const PRIVATE_ROUTE_PREFIXES = ['/dashboard', '/team', '/portal'];
const LAUNCH_SPLASH_HOLD_MS = 1000;
const LAUNCH_SPLASH_FADE_MS = 600;
const SPLASH_LOGO = require('./assets/gcc-logo.png');
const MOBILE_WEBVIEW_USER_AGENT = 'GrandCoastMobile/1.0';
const NATIVE_CONTACT_PATH = '/contact/';
const NATIVE_CONTACT_SUCCESS_MESSAGE = 'Thanks for sharing your project. We will be in touch soon.';
const MOBILE_CONTACT_REQUEST_HEADERS = { 'X-Grand-Coast-Mobile': '1' };
const EMPTY_NATIVE_CONTACT_FORM = {
  first_name: '',
  last_name: '',
  email: '',
  phone: '',
  project_type: '',
  location: '',
  message: '',
};

SplashScreen.setOptions({ duration: 0, fade: false });
SplashScreen.preventAutoHideAsync().catch(() => {});

const Drawer = createDrawerNavigator();
const SessionContext = createContext(null);
const SharedWebViewContext = createContext({
  consumeLogoutRequest: () => false,
  hideLaunchSplash: () => Promise.resolve(),
  launchSplashVisible: true,
  navigate: () => {},
  requestLogout: () => {},
  setCurrentPath: () => {},
  webViewRef: null,
});
const NativeShellContext = createContext({
  activeTab: null,
  activeWebPath: null,
  setActiveTab: () => {},
  setActiveWebPath: () => {},
});

const transparentNavigationTheme = {
  ...DefaultTheme,
  colors: {
    ...DefaultTheme.colors,
    background: 'transparent',
  },
};

const clientDrawerPages = [
  { label: 'Services', icon: 'construct-outline', path: '/services/', tab: 'Projects' },
  { label: 'Projects', icon: 'images-outline', path: '/projects/', tab: 'Projects' },
  { label: 'Process', icon: 'git-branch-outline', path: '/process/', tab: 'Projects' },
  { label: 'Contact', icon: 'chatbubble-ellipses-outline', path: '/contact/', tab: 'Contact' },
];

const employeeDrawerPages = [
  { label: 'Overview', icon: 'home-outline', path: EMPLOYEE_WORKSPACE_PATH, tab: 'Workspace' },
  { label: 'Projects', icon: 'folder-outline', path: EMPLOYEE_PROJECTS_PATH, tab: 'Workspace' },
  { label: 'Tasks', icon: 'checkmark-outline', path: '/team/tasks/', tab: 'Workspace' },
  { label: 'Calendar', icon: 'calendar-outline', path: '/team/calendar/', tab: 'Workspace' },
  { label: 'Time', icon: 'time-outline', path: '/team/time/', tab: 'Workspace' },
  { label: 'Media', icon: 'images-outline', path: '/team/media/', tab: 'Workspace' },
  { label: 'Profile', icon: 'person-circle-outline', path: '/team/profile/', tab: 'Workspace' },
];

const tabIcons = {
  Projects: ['images-outline', 'images'],
  Contact: ['chatbubble-ellipses-outline', 'chatbubble-ellipses'],
  Workspace: ['briefcase-outline', 'briefcase'],
};

const employeeTabIcons = {
  Dashboard: ['home-outline', 'home'],
  Workspace: ['briefcase-outline', 'briefcase'],
  More: ['menu-outline', 'menu-outline'],
};

const employeeBottomTabs = [
  { label: 'Dashboard', name: 'Dashboard', path: EMPLOYEE_WORKSPACE_PATH },
  { label: 'Workspace', name: 'Workspace', path: EMPLOYEE_PROJECTS_PATH },
  { label: 'More', name: 'More', path: null },
];

const clientBottomTabs = [
  { label: 'Projects', name: 'Projects', path: '/projects/' },
  { label: 'Contact', name: 'Contact', path: '/contact/' },
  { label: 'Workspace', name: 'Workspace', path: null },
];

const employeeMorePages = [
  { label: 'Privacy Policy', icon: 'shield-checkmark-outline', path: PRIVACY_PATH },
  { label: 'Terms of Service', icon: 'document-text-outline', path: TERMS_PATH },
  { label: 'Log out', icon: 'log-out-outline', path: EMPLOYEE_WORKSPACE_PATH, action: 'logout' },
  { label: 'Delete account', icon: 'trash-outline', path: ACCOUNT_DELETE_PATH, danger: true },
];

const employeeMoreContactPage = {
  label: 'Contact Grand Coast',
  icon: 'chatbubble-ellipses-outline',
};

const employeeDrawerLogout = employeeMorePages[2];

const MOBILE_CHROME_SCRIPT = [
  '(function () {',
  '  try {',
  "    var styleId = 'grand-coast-mobile-webview-chrome';",
  '    var style = document.getElementById(styleId);',
  '',
  '    if (!style) {',
  "      style = document.createElement('style');",
  '      style.id = styleId;',
  '      (document.head || document.documentElement).appendChild(style);',
  '    }',
  '',
  "    style.textContent = '.site-header, .site-footer, .portal-header, .portal-footer, .admin-topbar, .staging-bar, .portal-staging-bar, .admin-workspace-notice { display: none !important; } .auth-site .auth-card > .text-link { display: none !important; }';",
  '  } catch (error) {',
  '    // The page can still render if a WebView engine rejects the style injection.',
  '  }',
  '',
  '  true;',
  '})();',
].join('\n');

const MOBILE_LOGOUT_SCRIPT = [
  '(function () {',
  '  try {',
  '    var form = document.querySelector(\'form[action$="/accounts/logout/"]\');',
  '    if (!form) {',
  '      return true;',
  '    }',
  '    if (typeof form.requestSubmit === \'function\') {',
  '      form.requestSubmit();',
  '    } else {',
  '      form.submit();',
  '    }',
  '  } catch (error) {',
  '    // The existing Django logout form remains the source of truth.',
  '  }',
  '  true;',
  '})();',
].join('\n');

function useSession() {
  return useContext(SessionContext);
}

function pageUrl(path) {
  const normalizedPath = path && path.startsWith('/') ? path : '/' + (path || '');
  return WEB_APP_URL + normalizedPath;
}

function encodeFormBody(values) {
  return Object.entries(values)
    .map(([key, value]) => encodeURIComponent(key) + '=' + encodeURIComponent(String(value ?? '')))
    .join('&');
}

function extractCsrfToken(html) {
  const match = html.match(/name=["']csrfmiddlewaretoken["'][^>]*value=["']([^"']+)["']/i);
  return match ? match[1] : '';
}

async function submitNativeContactForm(values) {
  const contactUrl = pageUrl(NATIVE_CONTACT_PATH);
  const formResponse = await fetch(contactUrl, {
    credentials: 'include',
    headers: {
      Accept: 'text/html',
      ...MOBILE_CONTACT_REQUEST_HEADERS,
    },
  });

  if (!formResponse.ok) {
    throw new Error('The contact form could not be loaded.');
  }

  const csrfToken = extractCsrfToken(await formResponse.text());
  if (!csrfToken) {
    throw new Error('The contact form security token could not be loaded.');
  }

  const response = await fetch(contactUrl, {
    body: encodeFormBody({
      csrfmiddlewaretoken: csrfToken,
      ...values,
    }),
    credentials: 'include',
    headers: {
      Accept: 'text/html',
      'Content-Type': 'application/x-www-form-urlencoded',
      'X-CSRFToken': csrfToken,
      Referer: contactUrl,
      ...MOBILE_CONTACT_REQUEST_HEADERS,
    },
    method: 'POST',
  });
  const responseHtml = await response.text();

  if (!response.ok || !responseHtml.includes(NATIVE_CONTACT_SUCCESS_MESSAGE)) {
    throw new Error('The contact message could not be sent.');
  }
}

function validateNativeContactForm(values) {
  const requiredFields = ['first_name', 'last_name', 'email', 'project_type', 'location', 'message'];
  if (requiredFields.some((field) => !values[field].trim())) {
    return 'Please complete all required fields.';
  }

  if (!/^\S+@\S+\.\S+$/.test(values.email.trim())) {
    return 'Enter a valid email address.';
  }

  return '';
}

function relativePathFromUrl(urlOrPath) {
  const value = String(urlOrPath || '');
  const withoutOrigin = value.replace(/^https?:\/\/[^/]+/i, '');
  if (!withoutOrigin) {
    return HOME_PATH;
  }

  return withoutOrigin.startsWith('/') ? withoutOrigin : '/' + withoutOrigin;
}

function pathnameFromUrl(urlOrPath) {
  return relativePathFromUrl(urlOrPath).split(/[?#]/)[0] || HOME_PATH;
}

function isLoginPath(pathname) {
  return pathname === '/accounts/login' || pathname.startsWith(AUTH_PATH);
}

function isPrivatePath(pathname) {
  return PRIVATE_ROUTE_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(prefix + '/'),
  );
}

function workspaceKindFromPath(pathname) {
  if (pathname === '/team' || pathname.startsWith('/team/')) {
    return 'employee';
  }

  if (pathname === '/portal' || pathname.startsWith('/portal/')) {
    return 'client';
  }

  return null;
}

function isInternalUrl(url) {
  return (
    url === WEB_APP_URL ||
    url.startsWith(WEB_APP_URL + '/') ||
    url.startsWith(WEB_APP_URL + '?') ||
    url.startsWith(WEB_APP_URL + '#')
  );
}

function openExternalUrl(url) {
  Linking.openURL(url).catch(() => {});
  return false;
}

function AppHeader({ navigation }) {
  const insets = useSafeAreaInsets();
  const { navigate } = useContext(SharedWebViewContext);
  const { setActiveTab, setActiveWebPath } = useContext(NativeShellContext);
  const { workspaceKind, workspacePath } = useSession();

  const openProfile = useCallback(() => {
    const isEmployee = workspaceKind === 'employee';
    const profilePath = isEmployee ? EMPLOYEE_PROFILE_PATH : workspacePath || CLIENT_WORKSPACE_PATH;
    setActiveTab('Workspace');
    setActiveWebPath(profilePath);
    navigate(profilePath);
  }, [navigate, setActiveTab, setActiveWebPath, workspaceKind, workspacePath]);

  return (
    <View style={[styles.header, { paddingTop: insets.top }]}>
      <View style={styles.headerRow}>
        <Pressable
          accessibilityLabel="Open side navigation"
          hitSlop={10}
          onPress={() => navigation.openDrawer()}
          style={styles.headerButton}
        >
          <Ionicons color={colors.white} name="menu-outline" size={27} />
        </Pressable>

        <View style={styles.headerBrand}>
          <Text style={styles.headerTitle}>Grand Coast</Text>
          <Text style={styles.headerSubtitle}>Construction Inc.</Text>
        </View>

        <Pressable
          accessibilityLabel={workspaceKind === 'employee' ? 'Open profile' : 'Open workspace'}
          hitSlop={10}
          onPress={openProfile}
          style={styles.headerButton}
        >
          <Ionicons color={colors.white} name="person-circle-outline" size={28} />
        </Pressable>
      </View>
    </View>
  );
}

function NativeDrawerItem({ navigation, page, isEmployee }) {
  const { navigate } = useContext(SharedWebViewContext);
  const { setActiveTab, setActiveWebPath } = useContext(NativeShellContext);

  return (
    <DrawerItem
      activeBackgroundColor={isEmployee ? 'rgba(255, 255, 255, 0.12)' : undefined}
      activeTintColor={isEmployee ? colors.white : colors.blue}
      icon={({ color, size }) => (
        <Ionicons color={color} name={page.icon} size={size} />
      )}
      inactiveTintColor={isEmployee ? '#F5F7FA' : undefined}
      label={page.label}
      labelStyle={isEmployee ? styles.employeeDrawerItemLabel : styles.drawerItemLabel}
      onPress={() => {
        setActiveTab(page.tab);
        setActiveWebPath(page.path);
        navigate(page.path);
        navigation.closeDrawer();
      }}
      pressColor={isEmployee ? 'rgba(255, 255, 255, 0.08)' : '#EDF2F8'}
      style={isEmployee ? styles.employeeDrawerItem : styles.drawerItem}
    />
  );
}

function NativeDrawerAction({ action, navigation }) {
  const { requestLogout } = useContext(SharedWebViewContext);
  const { setActiveTab, setActiveWebPath } = useContext(NativeShellContext);

  return (
    <DrawerItem
      activeBackgroundColor="rgba(255, 255, 255, 0.12)"
      activeTintColor={colors.white}
      icon={({ color, size }) => <Ionicons color={color} name={action.icon} size={size} />}
      inactiveTintColor="#F5F7FA"
      label={action.label}
      labelStyle={styles.employeeDrawerItemLabel}
      onPress={() => {
        setActiveTab('Workspace');
        setActiveWebPath(EMPLOYEE_WORKSPACE_PATH);
        requestLogout();
        navigation.closeDrawer();
      }}
      pressColor="rgba(255, 255, 255, 0.08)"
      style={styles.employeeDrawerItem}
    />
  );
}

function AppDrawerContent({ navigation, ...props }) {
  const { isAuthenticated, workspaceKind, workspacePath } = useSession();
  const isEmployee = workspaceKind === 'employee';
  const pages = isEmployee ? employeeDrawerPages : clientDrawerPages;

  const accountPages = useMemo(
    () => [
      {
        label: 'Workspace',
        icon: 'briefcase-outline',
        path: workspacePath || CLIENT_WORKSPACE_PATH,
        tab: 'Workspace',
      },
    ],
    [workspacePath],
  );

  if (!isAuthenticated) {
    return null;
  }

  return (
    <DrawerContentScrollView
      {...props}
      contentContainerStyle={isEmployee ? styles.employeeDrawerContent : styles.drawerContent}
      showsVerticalScrollIndicator={false}
    >
      {isEmployee ? (
        <>
          <View style={styles.employeeDrawerTopRule} />
          <Text style={[styles.drawerSectionLabel, styles.employeeDrawerSectionLabel]}>My Workspace</Text>
          {pages.map((page) => (
            <NativeDrawerItem isEmployee key={page.path} navigation={navigation} page={page} />
          ))}
          <View style={styles.employeeDrawerBottomRule} />
          <NativeDrawerAction action={employeeDrawerLogout} navigation={navigation} />
        </>
      ) : (
        <>
          <View style={styles.drawerBrand}>
            <View style={styles.drawerMark}>
              <Text style={styles.drawerMarkText}>GC</Text>
            </View>
            <View>
              <Text style={styles.drawerBrandTitle}>Grand Coast</Text>
              <Text style={styles.drawerBrandSubtitle}>Construction Inc.</Text>
            </View>
          </View>

          <Text style={styles.drawerSectionLabel}>Explore</Text>
          {pages.map((page) => (
            <NativeDrawerItem key={page.path} navigation={navigation} page={page} />
          ))}

          <Text style={[styles.drawerSectionLabel, styles.drawerSectionLabelSpaced]}>Account</Text>
          {accountPages.map((page) => (
            <NativeDrawerItem key={page.path} navigation={navigation} page={page} />
          ))}

          <View style={styles.drawerFooter}>
            <Text style={styles.drawerFooterText}>Thoughtful construction.</Text>
            <Text style={styles.drawerFooterText}>Clear communication.</Text>
          </View>
        </>
      )}
    </DrawerContentScrollView>
  );
}

function useWebViewChrome(webViewRef) {
  return useCallback(() => {
    webViewRef.current?.injectJavaScript(MOBILE_CHROME_SCRIPT);
  }, [webViewRef]);
}

function SignInGate({ webViewRef }) {
  const pendingWorkspacePathRef = useRef(null);
  const {
    isAuthenticated,
    markAuthenticated,
    markUnauthenticated,
    updateWorkspacePath,
  } = useSession();
  const {
    consumeLogoutRequest,
    hideLaunchSplash,
    launchSplashVisible,
    setCurrentPath,
  } = useContext(SharedWebViewContext);
  const [canGoBack, setCanGoBack] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const injectMobileChrome = useWebViewChrome(webViewRef);
  const loginSource = useMemo(() => ({ uri: pageUrl(AUTH_PATH) }), []);

  useEffect(() => {
    if (Platform.OS !== 'android') {
      return undefined;
    }

    const subscription = BackHandler.addEventListener('hardwareBackPress', () => {
      if (!canGoBack) {
        return false;
      }

      webViewRef.current?.goBack();
      return true;
    });

    return () => subscription.remove();
  }, [canGoBack, webViewRef]);

  const handleNavigationStateChange = (state) => {
    setCanGoBack(Boolean(state.canGoBack));

    const relativePath = relativePathFromUrl(state.url);
    const pathname = pathnameFromUrl(relativePath);
    setCurrentPath(relativePath);

    if (isPrivatePath(pathname)) {
      if (isAuthenticated) {
        updateWorkspacePath(relativePath);
      } else {
        pendingWorkspacePathRef.current = relativePath;
      }
    } else if (isLoginPath(pathname)) {
      pendingWorkspacePathRef.current = null;
      if (isAuthenticated) {
        markUnauthenticated();
      }
    }
  };

  const handleRequest = (request) => {
    const requestUrl = request.url;

    if (!isInternalUrl(requestUrl)) {
      return openExternalUrl(requestUrl);
    }

    if (pathnameFromUrl(requestUrl) === HOME_PATH) {
      return false;
    }

    return true;
  };

  const handleLoadEnd = (event) => {
    setIsLoading(false);
    injectMobileChrome();

    const loadedPath = relativePathFromUrl(event?.nativeEvent?.url || AUTH_PATH);
    setCurrentPath(loadedPath);
    const pendingWorkspacePath = pendingWorkspacePathRef.current;
    pendingWorkspacePathRef.current = null;
    if (consumeLogoutRequest()) {
      webViewRef.current?.injectJavaScript(MOBILE_LOGOUT_SCRIPT);
    }
    hideLaunchSplash().then(() => {
      if (pendingWorkspacePath && !isAuthenticated) {
        markAuthenticated(pendingWorkspacePath);
      }
    });
  };

  const handleError = () => {
    pendingWorkspacePathRef.current = null;
    setHasError(true);
    setIsLoading(false);
    hideLaunchSplash();
  };

  return (
    <View style={styles.authGate}>
      <WebView
        allowsBackForwardNavigationGestures
        domStorageEnabled
        injectedJavaScript={MOBILE_CHROME_SCRIPT}
        injectedJavaScriptBeforeContentLoaded={MOBILE_CHROME_SCRIPT}
        javaScriptEnabled
        onError={handleError}
        onLoadEnd={handleLoadEnd}
        onLoadStart={() => {
          setHasError(false);
          setIsLoading(true);
        }}
        onMessage={() => {}}
        onNavigationStateChange={handleNavigationStateChange}
        onShouldStartLoadWithRequest={handleRequest}
        originWhitelist={['http://*', 'https://*']}
        ref={webViewRef}
        renderError={() => null}
        sharedCookiesEnabled
        source={loginSource}
        startInLoadingState
        style={styles.webView}
        testID="webview-sign-in"
        thirdPartyCookiesEnabled
        userAgent={MOBILE_WEBVIEW_USER_AGENT}
      />

      {isLoading && !launchSplashVisible && !hasError ? (
        <View pointerEvents="none" style={styles.loadingOverlay}>
          <ActivityIndicator color={colors.blue} size="large" />
          <Text style={styles.loadingText}>Loading sign in...</Text>
        </View>
      ) : null}

      {hasError ? (
        <View style={styles.errorOverlay}>
          <Ionicons color={colors.blue} name="cloud-offline-outline" size={42} />
          <Text style={styles.errorTitle}>Unable to reach Grand Coast</Text>
          <Text style={styles.errorText}>
            Check that the Django server is running and that the app is using the right local network address.
          </Text>
          <Pressable onPress={() => webViewRef.current?.reload()} style={styles.retryButton}>
            <Text style={styles.retryButtonText}>Try again</Text>
          </Pressable>
        </View>
      ) : null}

    </View>
  );
}

function EmployeeMoreItem({ page, onPress }) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={styles.moreItem}
    >
      <Ionicons color={page.danger ? colors.danger : colors.blue} name={page.icon} size={23} />
      <Text style={[styles.moreItemLabel, page.danger && styles.moreItemDanger]}>{page.label}</Text>
      <Ionicons color={page.danger ? colors.danger : colors.muted} name="chevron-forward-outline" size={19} />
    </Pressable>
  );
}

function NativeContactField({
  autoCapitalize = 'sentences',
  keyboardType,
  label,
  multiline = false,
  onChangeText,
  placeholder,
  testID,
  value,
}) {
  return (
    <View style={styles.nativeContactField}>
      <Text style={styles.nativeContactFieldLabel}>{label}</Text>
      <TextInput
        autoCapitalize={autoCapitalize}
        autoCorrect={false}
        keyboardType={keyboardType}
        multiline={multiline}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor="#94A3B8"
        style={[styles.nativeContactInput, multiline && styles.nativeContactMessageInput]}
        testID={testID}
        value={value}
      />
    </View>
  );
}

function EmployeeContactScreen({ onBack }) {
  const [form, setForm] = useState(() => ({ ...EMPTY_NATIVE_CONTACT_FORM }));
  const [status, setStatus] = useState('idle');
  const [submitError, setSubmitError] = useState('');

  const updateField = useCallback((field, value) => {
    setForm((currentForm) => ({ ...currentForm, [field]: value }));
    setStatus((currentStatus) => (currentStatus === 'success' ? 'idle' : currentStatus));
    setSubmitError('');
  }, []);

  const submit = useCallback(async () => {
    const validationError = validateNativeContactForm(form);
    if (validationError) {
      setStatus('idle');
      setSubmitError(validationError);
      return;
    }

    setStatus('submitting');
    setSubmitError('');
    try {
      await submitNativeContactForm(form);
      setForm({ ...EMPTY_NATIVE_CONTACT_FORM });
      setStatus('success');
    } catch {
      setStatus('idle');
      setSubmitError("We couldn't send your message. Check your connection and try again.");
    }
  }, [form]);

  const isSubmitting = status === 'submitting';

  return (
    <View style={styles.nativeContactScreen} testID="employee-contact-form">
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.nativeContactKeyboard}
      >
        <ScrollView
          contentContainerStyle={styles.nativeContactContent}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <Pressable
            accessibilityLabel="Back to More"
            accessibilityRole="button"
            onPress={onBack}
            style={styles.nativeContactBack}
            testID="employee-contact-back"
          >
            <Ionicons color={colors.blue} name="arrow-back-outline" size={20} />
            <Text style={styles.nativeContactBackLabel}>More</Text>
          </Pressable>

          <Text style={styles.nativeContactKicker}>Employee support</Text>
          <Text style={styles.nativeContactTitle}>Contact Grand Coast</Text>
          <Text style={styles.nativeContactIntro}>
            Send a message directly to the Grand Coast team.
          </Text>

          {status === 'success' ? (
            <View accessibilityLiveRegion="polite" style={[styles.nativeContactNotice, styles.nativeContactSuccess]}>
              <Text style={styles.nativeContactNoticeTitle}>Message sent</Text>
              <Text style={styles.nativeContactNoticeBody}>
                Thanks for reaching out. We will be in touch soon.
              </Text>
            </View>
          ) : null}

          {submitError ? (
            <View accessibilityLiveRegion="polite" style={[styles.nativeContactNotice, styles.nativeContactError]}>
              <Text style={styles.nativeContactNoticeTitle}>Unable to send</Text>
              <Text style={styles.nativeContactNoticeBody}>{submitError}</Text>
            </View>
          ) : null}

          <View style={styles.nativeContactCard}>
            <NativeContactField
              label="First name"
              onChangeText={(value) => updateField('first_name', value)}
              placeholder="First name"
              testID="employee-contact-first-name"
              value={form.first_name}
            />
            <NativeContactField
              label="Last name"
              onChangeText={(value) => updateField('last_name', value)}
              placeholder="Last name"
              testID="employee-contact-last-name"
              value={form.last_name}
            />
            <NativeContactField
              autoCapitalize="none"
              keyboardType="email-address"
              label="Email"
              onChangeText={(value) => updateField('email', value)}
              placeholder="you@example.com"
              testID="employee-contact-email"
              value={form.email}
            />
            <NativeContactField
              keyboardType="phone-pad"
              label="Phone"
              onChangeText={(value) => updateField('phone', value)}
              placeholder="Optional"
              testID="employee-contact-phone"
              value={form.phone}
            />
            <NativeContactField
              label="Project type"
              onChangeText={(value) => updateField('project_type', value)}
              placeholder="Remodel, restoration, or other"
              testID="employee-contact-project-type"
              value={form.project_type}
            />
            <NativeContactField
              label="Location"
              onChangeText={(value) => updateField('location', value)}
              placeholder="City or project address"
              testID="employee-contact-location"
              value={form.location}
            />
            <NativeContactField
              label="Tell us about the project"
              multiline
              onChangeText={(value) => updateField('message', value)}
              placeholder="How can we help?"
              testID="employee-contact-message"
              value={form.message}
            />
            <Pressable
              accessibilityRole="button"
              disabled={isSubmitting}
              onPress={submit}
              style={[styles.nativeContactSubmit, isSubmitting && styles.nativeContactSubmitDisabled]}
              testID="employee-contact-submit"
            >
              {isSubmitting ? (
                <ActivityIndicator color={colors.white} />
              ) : (
                <Text style={styles.nativeContactSubmitText}>Send message</Text>
              )}
            </Pressable>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

function EmployeeMoreScreen() {
  const [showContactForm, setShowContactForm] = useState(false);
  const { navigate, requestLogout } = useContext(SharedWebViewContext);
  const { setActiveTab, setActiveWebPath } = useContext(NativeShellContext);
  const openPage = useCallback((page) => {
    setActiveTab('Workspace');
    setActiveWebPath(page.action === 'logout' ? EMPLOYEE_WORKSPACE_PATH : page.path);
    if (page.action === 'logout') {
      requestLogout();
      return;
    }

    navigate(page.path);
  }, [navigate, requestLogout, setActiveTab, setActiveWebPath]);
  const openContactForm = useCallback(() => {
    setShowContactForm(true);
  }, []);
  const closeContactForm = useCallback(() => {
    setShowContactForm(false);
  }, []);

  if (showContactForm) {
    return <EmployeeContactScreen onBack={closeContactForm} />;
  }

  return (
    <View style={styles.moreScreen}>
      <ScrollView contentContainerStyle={styles.moreContent} showsVerticalScrollIndicator={false}>
        <Text style={styles.moreSectionLabel}>Account & support</Text>
        {employeeMorePages.slice(0, 2).map((page) => (
          <EmployeeMoreItem
            key={page.path}
            onPress={() => openPage(page)}
            page={page}
          />
        ))}
        <EmployeeMoreItem page={employeeMoreContactPage} onPress={openContactForm} />

        <Text style={[styles.moreSectionLabel, styles.moreSectionLabelSpaced]}>Session</Text>
        {employeeMorePages.slice(2).map((page) => (
          <EmployeeMoreItem
            key={page.path}
            onPress={() => openPage(page)}
            page={page}
          />
        ))}
      </ScrollView>
    </View>
  );
}

function NativeTabBar({ activeTab, insets, isEmployee, onSelect }) {
  const icons = isEmployee ? employeeTabIcons : tabIcons;
  const tabs = isEmployee ? employeeBottomTabs : clientBottomTabs;

  return (
    <View
      style={[
        styles.tabBar,
        { height: 62 + insets.bottom, paddingBottom: 7 + insets.bottom },
      ]}
    >
      {tabs.map((tab) => {
        const focused = activeTab === tab.name;
        const [outline, filled] = icons[tab.name];

        return (
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ selected: focused }}
            key={tab.name}
            onPress={() => onSelect(tab.name)}
            style={styles.tabBarItem}
          >
            <Ionicons
              color={focused ? colors.gold : colors.muted}
              name={focused ? filled : outline}
              size={25}
            />
            <Text style={[styles.tabBarLabel, { color: focused ? colors.gold : colors.muted }]}>
              {tab.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function MainTabs() {
  const insets = useSafeAreaInsets();
  const { isAuthenticated, workspaceKind, workspacePath } = useSession();
  const { navigate, webViewRef } = useContext(SharedWebViewContext);
  const {
    activeTab,
    activeWebPath: selectedWebPath,
    setActiveTab,
    setActiveWebPath,
  } = useContext(NativeShellContext);
  const isEmployee = workspaceKind === 'employee';
  const isMore = isEmployee && activeTab === 'More';
  const tabBarHeight = 62 + insets.bottom;
  const activeWebPath = useMemo(() => {
    if (!isAuthenticated || isMore) {
      return null;
    }

    if (selectedWebPath) {
      return selectedWebPath;
    }

    if (isEmployee) {
      return activeTab === 'Dashboard' ? EMPLOYEE_WORKSPACE_PATH : EMPLOYEE_PROJECTS_PATH;
    }

    if (activeTab === 'Projects') {
      return '/projects/';
    }

    if (activeTab === 'Contact') {
      return '/contact/';
    }

    return workspacePath || CLIENT_WORKSPACE_PATH;
  }, [activeTab, isAuthenticated, isEmployee, isMore, selectedWebPath, workspacePath]);

  useEffect(() => {
    if (activeWebPath) {
      navigate(activeWebPath);
    }
  }, [activeWebPath, navigate]);

  const selectTab = useCallback((tabName) => {
    setActiveTab(tabName);
    if (tabName === 'More') {
      setActiveWebPath(null);
      return;
    }

    const tabPath = isEmployee
      ? tabName === 'Dashboard' ? EMPLOYEE_WORKSPACE_PATH : EMPLOYEE_PROJECTS_PATH
      : tabName === 'Projects' ? '/projects/'
        : tabName === 'Contact' ? '/contact/'
          : workspacePath || CLIENT_WORKSPACE_PATH;
    setActiveWebPath(tabPath);
  }, [isEmployee, setActiveTab, setActiveWebPath, workspacePath]);

  return (
    <View style={styles.mainTabs}>
      <View
        pointerEvents={isMore ? 'none' : 'auto'}
        style={[
          styles.mainTabsWebView,
          isAuthenticated && !isMore && { marginBottom: tabBarHeight },
          isMore && styles.mainTabsWebViewHidden,
        ]}
      >
        <SignInGate webViewRef={webViewRef} />
      </View>

      {isMore ? (
        <View style={[styles.nativeContentOverlay, { bottom: tabBarHeight }]}>
          <EmployeeMoreScreen />
        </View>
      ) : null}

      {isAuthenticated ? (
        <NativeTabBar
          activeTab={activeTab}
          insets={insets}
          isEmployee={isEmployee}
          onSelect={selectTab}
        />
      ) : null}
    </View>
  );
}

function AppShell() {
  const { isAuthenticated, workspaceKind } = useSession();
  const isEmployee = workspaceKind === 'employee';
  const [activeTab, setActiveTab] = useState(null);
  const [activeWebPath, setActiveWebPath] = useState(null);
  const validTabs = isEmployee ? employeeBottomTabs : clientBottomTabs;
  const selectedTab = !isAuthenticated
    ? null
    : validTabs.some((tab) => tab.name === activeTab)
      ? activeTab
      : isEmployee ? 'Dashboard' : 'Workspace';
  useEffect(() => {
    setActiveTab(isAuthenticated ? (isEmployee ? 'Dashboard' : 'Workspace') : null);
    setActiveWebPath(null);
  }, [isAuthenticated, isEmployee]);

  const nativeShellValue = useMemo(
    () => ({
      activeTab: selectedTab,
      activeWebPath,
      setActiveTab,
      setActiveWebPath,
    }),
    [activeWebPath, selectedTab],
  );

  return (
    <NativeShellContext.Provider value={nativeShellValue}>
      <View style={styles.appShell}>
        <NavigationContainer theme={transparentNavigationTheme}>
          <Drawer.Navigator
            drawerContent={(props) => <AppDrawerContent {...props} />}
            screenOptions={{
              drawerStyle: !isAuthenticated
                ? [styles.drawer, styles.hiddenDrawer]
                : isEmployee ? [styles.drawer, styles.employeeDrawer] : styles.drawer,
              drawerType: 'front',
              header: (props) => <AppHeader {...props} />,
              headerShown: isAuthenticated,
              overlayColor: 'rgba(16, 43, 78, 0.38)',
              swipeEnabled: isAuthenticated,
              swipeEdgeWidth: 36,
            }}
          >
            <Drawer.Screen component={MainTabs} name="Main" options={{ title: 'Grand Coast' }} />
          </Drawer.Navigator>
        </NavigationContainer>
      </View>
    </NativeShellContext.Provider>
  );
}

export default function App() {
  const sharedWebViewRef = useRef(null);
  const sharedWebViewPathRef = useRef(null);
  const sharedWebViewLogoutPendingRef = useRef(false);
  const launchSplashStartedAtRef = useRef(Date.now());
  const launchSplashHandledRef = useRef(false);
  const launchSplashOpacity = useRef(new Animated.Value(1)).current;
  const [launchSplashVisible, setLaunchSplashVisible] = useState(true);
  const [session, setSession] = useState({
    isAuthenticated: false,
    workspaceKind: null,
    workspacePath: null,
  });

  const markAuthenticated = useCallback((urlOrPath) => {
    const relativePath = relativePathFromUrl(urlOrPath);
    const pathname = pathnameFromUrl(relativePath);

    setSession({
      isAuthenticated: true,
      workspaceKind: workspaceKindFromPath(pathname),
      workspacePath: isPrivatePath(pathname) ? relativePath : null,
    });
  }, []);

  const markUnauthenticated = useCallback(() => {
    setSession({
      isAuthenticated: false,
      workspaceKind: null,
      workspacePath: null,
    });
  }, []);

  const setSharedWebViewPath = useCallback((urlOrPath) => {
    sharedWebViewPathRef.current = relativePathFromUrl(urlOrPath);
  }, []);

  const navigateSharedWebView = useCallback((path) => {
    const relativePath = relativePathFromUrl(path);
    if (sharedWebViewPathRef.current === relativePath) {
      return;
    }

    sharedWebViewPathRef.current = relativePath;
    sharedWebViewRef.current?.injectJavaScript(
      'window.location.assign(' + JSON.stringify(pageUrl(relativePath)) + '); true;',
    );
  }, []);

  const requestSharedWebViewLogout = useCallback(() => {
    const currentPath = sharedWebViewPathRef.current;
    if (pathnameFromUrl(currentPath) !== pathnameFromUrl(EMPLOYEE_WORKSPACE_PATH)) {
      sharedWebViewLogoutPendingRef.current = true;
      sharedWebViewPathRef.current = EMPLOYEE_WORKSPACE_PATH;
      sharedWebViewRef.current?.injectJavaScript(
        'window.location.assign(' + JSON.stringify(pageUrl(EMPLOYEE_WORKSPACE_PATH)) + '); true;',
      );
      return;
    }

    sharedWebViewLogoutPendingRef.current = false;
    sharedWebViewRef.current?.injectJavaScript(MOBILE_LOGOUT_SCRIPT);
  }, []);

  const consumeLogoutRequest = useCallback(() => {
    const isPending = sharedWebViewLogoutPendingRef.current;
    sharedWebViewLogoutPendingRef.current = false;
    return isPending;
  }, []);

  const hideLaunchSplash = useCallback(() => {
    if (launchSplashHandledRef.current) {
      return Promise.resolve();
    }

    launchSplashHandledRef.current = true;

    const elapsedMs = Date.now() - launchSplashStartedAtRef.current;
    const remainingHoldMs = Math.max(0, LAUNCH_SPLASH_HOLD_MS - elapsedMs);
    const hold = remainingHoldMs
      ? new Promise((resolve) => setTimeout(resolve, remainingHoldMs))
      : Promise.resolve();

    return hold
      .then(() => SplashScreen.hideAsync().catch(() => {}))
      .then(
        () => new Promise((resolve) => {
          Animated.timing(launchSplashOpacity, {
            duration: LAUNCH_SPLASH_FADE_MS,
            toValue: 0,
            useNativeDriver: true,
          }).start(() => {
            setLaunchSplashVisible(false);
            resolve();
          });
        }),
      );
  }, [launchSplashOpacity]);

  const updateWorkspacePath = useCallback((urlOrPath) => {
    const relativePath = relativePathFromUrl(urlOrPath);
    const pathname = pathnameFromUrl(relativePath);

    if (!isPrivatePath(pathname)) {
      return;
    }

    setSession((currentSession) => {
      const workspaceKind = currentSession.workspaceKind || workspaceKindFromPath(pathname);
      if (
        currentSession.workspaceKind === workspaceKind
        && currentSession.workspacePath === relativePath
      ) {
        return currentSession;
      }

      return {
        ...currentSession,
        workspaceKind,
        workspacePath: relativePath,
      };
    });
  }, []);

  const sessionValue = useMemo(
    () => ({
      ...session,
      markAuthenticated,
      markUnauthenticated,
      updateWorkspacePath,
    }),
    [markAuthenticated, markUnauthenticated, session, updateWorkspacePath],
  );

  const sharedWebViewValue = useMemo(
    () => ({
      navigate: navigateSharedWebView,
      consumeLogoutRequest,
      hideLaunchSplash,
      launchSplashVisible,
      requestLogout: requestSharedWebViewLogout,
      setCurrentPath: setSharedWebViewPath,
      webViewRef: sharedWebViewRef,
    }),
    [
      consumeLogoutRequest,
      hideLaunchSplash,
      launchSplashVisible,
      navigateSharedWebView,
      requestSharedWebViewLogout,
      setSharedWebViewPath,
    ],
  );

  return (
    <SafeAreaProvider>
      <SessionContext.Provider value={sessionValue}>
        <SharedWebViewContext.Provider value={sharedWebViewValue}>
          <View style={styles.mobileRoot}>
            <AppShell />
            {launchSplashVisible ? (
              <Animated.View
                pointerEvents="none"
                style={[styles.splashTransition, { opacity: launchSplashOpacity }]}
              >
                <Image source={SPLASH_LOGO} style={styles.splashTransitionLogo} />
              </Animated.View>
            ) : null}
          </View>
        </SharedWebViewContext.Provider>
      </SessionContext.Provider>
      <StatusBar
        backgroundColor={session.isAuthenticated ? colors.navy : colors.white}
        style={session.isAuthenticated ? 'light' : 'dark'}
      />
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  appShell: {
    flex: 1,
  },
  authGate: {
    backgroundColor: colors.white,
    flex: 1,
  },
  mobileRoot: {
    flex: 1,
  },
  hiddenDrawer: {
    width: 0,
  },
  mainTabs: {
    backgroundColor: colors.canvas,
    flex: 1,
    position: 'relative',
  },
  mainTabsWebView: {
    flex: 1,
  },
  mainTabsWebViewHidden: {
    bottom: 0,
    left: 0,
    opacity: 0,
    position: 'absolute',
    right: 0,
    top: 0,
  },
  nativeContentOverlay: {
    backgroundColor: colors.canvas,
    bottom: 0,
    elevation: 2,
    left: 0,
    position: 'absolute',
    right: 0,
    top: 0,
    zIndex: 2,
  },
  drawer: {
    backgroundColor: colors.white,
    width: 306,
  },
  employeeDrawer: {
    backgroundColor: colors.navy,
  },
  drawerBrand: {
    alignItems: 'center',
    borderBottomColor: colors.border,
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    gap: 12,
    marginBottom: 22,
    paddingBottom: 22,
    paddingHorizontal: 20,
    paddingTop: 12,
  },
  drawerBrandSubtitle: {
    color: colors.muted,
    fontSize: 11,
    letterSpacing: 0.7,
    marginTop: 2,
    textTransform: 'uppercase',
  },
  drawerBrandTitle: {
    color: colors.navy,
    fontFamily: Platform.select({ ios: 'Georgia', default: 'serif' }),
    fontSize: 20,
    fontWeight: '700',
  },
  drawerContent: {
    flexGrow: 1,
    paddingBottom: 20,
  },
  employeeDrawerContent: {
    backgroundColor: colors.navy,
    flexGrow: 1,
    paddingBottom: 24,
    paddingHorizontal: 10,
    paddingTop: 10,
  },
  employeeDrawerItem: {
    borderRadius: 8,
    marginHorizontal: 0,
    marginVertical: 2,
  },
  employeeDrawerItemLabel: {
    color: '#F5F7FA',
    fontSize: 15,
    fontWeight: '700',
    marginLeft: -8,
  },
  employeeDrawerSectionLabel: {
    color: '#AFC4E2',
    marginBottom: 12,
    marginHorizontal: 14,
    marginTop: 34,
  },
  employeeDrawerTopRule: {
    borderTopColor: 'rgba(255, 255, 255, 0.28)',
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  employeeDrawerBottomRule: {
    borderTopColor: 'rgba(255, 255, 255, 0.28)',
    borderTopWidth: StyleSheet.hairlineWidth,
    marginBottom: 8,
    marginTop: 'auto',
  },
  drawerFooter: {
    borderTopColor: colors.border,
    borderTopWidth: StyleSheet.hairlineWidth,
    marginHorizontal: 20,
    marginTop: 'auto',
    paddingTop: 18,
  },
  drawerFooterText: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 19,
  },
  drawerItem: {
    borderRadius: 12,
    marginHorizontal: 10,
    marginVertical: 1,
  },
  drawerItemLabel: {
    fontSize: 15,
    fontWeight: '600',
    marginLeft: -8,
  },
  nativeContactBack: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 6,
    marginBottom: 26,
  },
  nativeContactBackLabel: {
    color: colors.blue,
    fontSize: 14,
    fontWeight: '800',
  },
  nativeContactCard: {
    backgroundColor: colors.white,
    borderColor: colors.border,
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    padding: 18,
  },
  nativeContactContent: {
    padding: 24,
    paddingBottom: 44,
  },
  nativeContactError: {
    backgroundColor: '#FFF4F3',
    borderColor: '#E8C4C0',
    borderWidth: 1,
  },
  nativeContactField: {
    marginBottom: 16,
  },
  nativeContactFieldLabel: {
    color: colors.navy,
    fontSize: 12,
    fontWeight: '800',
    marginBottom: 7,
  },
  nativeContactInput: {
    backgroundColor: '#FBFCFE',
    borderColor: '#CDD7E4',
    borderRadius: 6,
    borderWidth: 1,
    color: colors.ink,
    fontSize: 15,
    minHeight: 46,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  nativeContactIntro: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 21,
    marginBottom: 22,
    marginTop: 8,
  },
  nativeContactKeyboard: {
    flex: 1,
  },
  nativeContactKicker: {
    color: colors.blue,
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  nativeContactMessageInput: {
    minHeight: 120,
    textAlignVertical: 'top',
  },
  nativeContactNotice: {
    borderRadius: 10,
    marginBottom: 16,
    padding: 14,
  },
  nativeContactNoticeBody: {
    color: colors.muted,
    fontSize: 13,
    lineHeight: 19,
    marginTop: 4,
  },
  nativeContactNoticeTitle: {
    color: colors.navy,
    fontSize: 14,
    fontWeight: '800',
  },
  nativeContactScreen: {
    backgroundColor: colors.canvas,
    flex: 1,
  },
  nativeContactSubmit: {
    alignItems: 'center',
    backgroundColor: colors.blue,
    borderRadius: 10,
    justifyContent: 'center',
    marginTop: 2,
    minHeight: 50,
    paddingHorizontal: 20,
  },
  nativeContactSubmitDisabled: {
    opacity: 0.65,
  },
  nativeContactSubmitText: {
    color: colors.white,
    fontSize: 15,
    fontWeight: '800',
  },
  nativeContactSuccess: {
    backgroundColor: '#E9F7EF',
    borderColor: '#B9DFC7',
    borderWidth: 1,
  },
  nativeContactTitle: {
    color: colors.navy,
    fontFamily: Platform.select({ ios: 'Georgia', default: 'serif' }),
    fontSize: 30,
    fontWeight: '700',
    marginTop: 7,
  },
  moreContent: {
    padding: 24,
    paddingBottom: 34,
  },
  moreItem: {
    alignItems: 'center',
    backgroundColor: colors.white,
    borderColor: colors.border,
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    gap: 14,
    marginBottom: 12,
    minHeight: 66,
    paddingHorizontal: 18,
  },
  moreItemDanger: {
    color: colors.danger,
  },
  moreItemLabel: {
    color: colors.navy,
    flex: 1,
    fontSize: 15,
    fontWeight: '700',
  },
  moreScreen: {
    backgroundColor: colors.canvas,
    flex: 1,
  },
  moreSectionLabel: {
    color: colors.blue,
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 1.2,
    marginBottom: 12,
    textTransform: 'uppercase',
  },
  moreSectionLabelSpaced: {
    marginTop: 22,
  },
  drawerMark: {
    alignItems: 'center',
    backgroundColor: colors.navy,
    borderRadius: 12,
    height: 46,
    justifyContent: 'center',
    width: 46,
  },
  drawerMarkText: {
    color: colors.gold,
    fontSize: 16,
    fontWeight: '800',
    letterSpacing: 1,
  },
  drawerSectionLabel: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 1.3,
    marginBottom: 6,
    marginHorizontal: 20,
    textTransform: 'uppercase',
  },
  drawerSectionLabelSpaced: {
    marginTop: 22,
  },
  errorOverlay: {
    alignItems: 'center',
    backgroundColor: colors.canvas,
    bottom: 0,
    justifyContent: 'center',
    left: 0,
    padding: 30,
    position: 'absolute',
    right: 0,
    top: 0,
  },
  errorText: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 21,
    maxWidth: 320,
    textAlign: 'center',
  },
  errorTitle: {
    color: colors.navy,
    fontSize: 20,
    fontWeight: '800',
    marginBottom: 8,
    marginTop: 16,
  },
  header: {
    backgroundColor: colors.navy,
  },
  headerBrand: {
    flex: 1,
    marginHorizontal: 14,
  },
  headerButton: {
    alignItems: 'center',
    height: 44,
    justifyContent: 'center',
    width: 44,
  },
  headerRow: {
    alignItems: 'center',
    flexDirection: 'row',
    height: 58,
    paddingHorizontal: 10,
  },
  headerSubtitle: {
    color: '#CAD6E7',
    fontSize: 10,
    letterSpacing: 1.1,
    marginTop: 1,
    textTransform: 'uppercase',
  },
  headerTitle: {
    color: colors.white,
    fontFamily: Platform.select({ ios: 'Georgia', default: 'serif' }),
    fontSize: 20,
    fontWeight: '700',
  },
  loadingOverlay: {
    alignItems: 'center',
    backgroundColor: 'rgba(245, 247, 250, 0.92)',
    bottom: 0,
    justifyContent: 'center',
    left: 0,
    position: 'absolute',
    right: 0,
    top: 0,
  },
  loadingText: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: '600',
    marginTop: 12,
  },
  retryButton: {
    backgroundColor: colors.blue,
    borderRadius: 10,
    marginTop: 22,
    paddingHorizontal: 24,
    paddingVertical: 12,
  },
  retryButtonText: {
    color: colors.white,
    fontSize: 14,
    fontWeight: '800',
  },
  splashTransition: {
    alignItems: 'center',
    backgroundColor: colors.white,
    bottom: 0,
    justifyContent: 'center',
    left: 0,
    position: 'absolute',
    right: 0,
    top: 0,
  },
  splashTransitionLogo: {
    height: 220,
    width: 220,
  },
  tabBar: {
    bottom: 0,
    flexDirection: 'row',
    backgroundColor: colors.white,
    borderTopColor: colors.border,
    borderTopWidth: StyleSheet.hairlineWidth,
    elevation: 12,
    left: 0,
    paddingTop: 6,
    position: 'absolute',
    right: 0,
    zIndex: 10,
  },
  tabBarItem: {
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
  },
  tabBarLabel: {
    fontSize: 11,
    fontWeight: '700',
  },
  webView: {
    backgroundColor: colors.canvas,
    flex: 1,
  },
});
