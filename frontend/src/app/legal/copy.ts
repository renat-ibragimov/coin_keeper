type Document = {
  title: string;
  updated: string;
  intro: string;
  navigation: string;
  back: string;
  other: string;
  sections: { title: string; paragraphs: string[] }[];
};

export const legalCopy: Record<'uk' | 'en', Record<'privacy' | 'terms', Document>> = {
  uk: {
    privacy: {
      title: 'Політика конфіденційності',
      updated: 'Оновлено: 16 вересня 2026 року',
      intro:
        'Bakost Numismatics — сервіс для ведення нумізматичного каталогу, особистої колекції та витрат. Ця політика пояснює, які дані обробляються під час користування сайтом.',
      navigation: 'Навігація документами',
      back: 'Назад до сайту',
      other: 'Умови користування',
      sections: [
        {
          title: 'Хто обробляє дані та як зв’язатися',
          paragraphs: [
            'Сервіс Bakost Numismatics веде команда Bakost Numismatics. З питань ваших даних скористайтеся кнопкою «Підтримка» внизу сайту: вона відкриває нашого бота в Telegram. Щоб ми могли знайти обліковий запис, вкажіть пов’язану з ним адресу електронної пошти. Не надсилайте пароль, коди входу чи інші секрети.',
          ],
        },
        {
          title: 'Які дані ми отримуємо',
          paragraphs: [
            'Для облікового запису ми зберігаємо адресу електронної пошти, необов’язкове ім’я та фото профілю, відомості про підтвердження пошти, хеш пароля (якщо ви встановили пароль) і налаштування інтерфейсу. Для входу й захисту сервісу також обробляються відомості про сесії, IP-адреса, дані браузера та тимчасові дані для підтвердження пошти чи відновлення пароля.',
            'Ви самі додаєте відомості про колекцію й витрати: монети, кількість, стан, місця зберігання, продавців, дати й місця придбання, ціни, валюти, нотатки та зображення. Деякі з цих відомостей можуть бути для вас приватними; додавайте лише те, що хочете зберігати в сервісі.',
            'Коли ви звертаєтеся до підтримки через Telegram, ми отримуємо доступні Telegram ID, ім’я користувача та ім’я, а також ваші повідомлення й вкладення. Якщо ви відкрили підтримку із сайту, звернення може бути пов’язане з вашим обліковим записом. Команда підтримки отримує ці повідомлення в Telegram.',
          ],
        },
        {
          title: 'Google Sign-In',
          paragraphs: [
            'Вхід через Google є необов’язковим. Якщо ви його обираєте або прив’язуєте Google до облікового запису, ми запитуємо базові дані профілю: ідентифікатор Google, адресу електронної пошти, статус її підтвердження та ім’я, якщо воно доступне. Ідентифікатор і адресу пошти на момент прив’язування ми зберігаємо для подальшого входу; ім’я може використовуватися як ім’я профілю. Ми не отримуємо ваш пароль Google і не запитуємо доступу до Gmail чи Google Drive.',
          ],
        },
        {
          title: 'Cookies і сховище браузера',
          paragraphs: [
            'Ми використовуємо необхідні cookies для входу та підтримання сесії, а під час входу через Google — тимчасові дані для безпечного завершення авторизації. Без них відповідні способи входу не працюватимуть.',
            'Сховище браузера запам’ятовує ваш вибір мови, теми, вигляду списків і функції «Запам’ятати мене». Ми не використовуємо рекламні трекери чи сторонні трекери аналітики.',
          ],
        },
        {
          title: 'Мета обробки та передача даних',
          paragraphs: [
            'Ми використовуємо ці дані, щоб створювати облікові записи, забезпечувати вхід, зберігати вашу колекцію й витрати, застосовувати налаштування, відповідати на звернення та запобігати зловживанням. Дані облікового запису й колекції зберігаються в захищеній серверній інфраструктурі сервісу. Доступ до ваших записів і завантажених зображень обмежено; посилання на зображення, надане вам сервісом, може відкрити й інша особа, якщо ви ним поділитеся.',
            'Google обробляє дані, потрібні для обраного вами входу через Google. Для листів про підтвердження пошти й відновлення пароля ми використовуємо Resend, якому передаються адреса одержувача та дані, необхідні для доставки листа. Telegram обробляє ваші звернення до підтримки та вкладення згідно зі своїми правилами.',
            'Якщо ввімкнено переклад через Anthropic, назва нового місця зберігання, яку ви ввели, може бути надіслана Anthropic для перекладу. Службові інструменти також можуть надсилати назви монет із каталогу. Це не означає передачу всього облікового запису чи колекції. Не вводьте особисті відомості в назву місця зберігання, якщо не бажаєте такої передачі.',
            'Каталог і курси валют можуть оновлюватися із зовнішніх джерел без передачі їм вашої колекції. Якщо ви відкриваєте зовнішнє джерело чи сторінку пожертви monobank, відповідний сайт обробляє дані вашого відвідування за власними правилами. Окремі каталожні зображення можуть завантажуватися безпосередньо із зовнішнього джерела.',
          ],
        },
        {
          title: 'Зберігання, безпека та ваші права',
          paragraphs: [
            'Дані облікового запису й колекції зберігаються, доки обліковий запис існує або доки ці дані потрібні для роботи сервісу чи виконання законних вимог. Після видалення основних даних технічні записи чи резервні копії, якщо вони є, можуть залишатися протягом обмеженого часу. Точний строк залежить від призначення даних і вимог закону; єдиного строку для всіх даних немає.',
            'Для захисту даних використовуються шифроване HTTPS-з’єднання, обмеження доступу, захищене зберігання паролів і контроль доступу до особистих матеріалів. Жоден інтернет-сервіс не може гарантувати абсолютну безпеку.',
            'Ви можете попросити доступ до своїх даних, їх виправлення, копію або видалення, а також інформацію про їх обробку. Автоматичного видалення облікового запису чи експорту всіх даних у інтерфейсі поки немає: зверніться до підтримки, і ми розглянемо запит за застосовним законодавством України. Ви також можете звернутися зі скаргою до Уповноваженого Верховної Ради України з прав людини або до суду.',
          ],
        },
        {
          title: 'Зміни політики',
          paragraphs: [
            'Ми можемо оновлювати цю політику разом зі змінами сервісу. Актуальна редакція та дата оновлення завжди розміщені на цій сторінці.',
          ],
        },
      ],
    },
    terms: {
      title: 'Умови користування',
      updated: 'Оновлено: 16 вересня 2026 року',
      intro:
        'Ці умови регулюють використання Bakost Numismatics. Створюючи обліковий запис або користуючись сервісом, ви погоджуєтеся з ними.',
      navigation: 'Навігація документами',
      back: 'Назад до сайту',
      other: 'Політика конфіденційності',
      sections: [
        {
          title: 'Сервіс і обліковий запис',
          paragraphs: [
            'Bakost Numismatics надає інструменти для перегляду нумізматичного каталогу, ведення особистої колекції, витрат і пов’язаних налаштувань. Для особистих функцій потрібен обліковий запис. Ви відповідаєте за правильність наданих даних, захист своїх облікових даних і дії під своїм обліковим записом.',
            'Вхід через Google є додатковим способом авторизації. Якщо ви прив’язуєте Google до облікового запису, ви дозволяєте сервісу використовувати отримані дані для входу згідно з Політикою конфіденційності.',
            'Ви можете припинити користування сервісом і звернутися до підтримки із запитом на видалення облікового запису. Обробка та зберігання даних після такого запиту здійснюються відповідно до Політики конфіденційності.',
          ],
        },
        {
          title: 'Ваші матеріали',
          paragraphs: [
            'Ви зберігаєте права на матеріали, які належать вам. Завантажуючи матеріали до сервісу, ви підтверджуєте, що маєте право їх використовувати, і надаєте нам необхідний дозвіл зберігати, обробляти та відображати їх виключно для роботи функцій сервісу. Не розміщуйте незаконний або шкідливий вміст.',
            'Ми можемо видалити матеріали або обмежити доступ до них, якщо вони порушують ці умови, закон або права інших осіб.',
            'Особисті записи призначені для вашого облікового запису. Не використовуйте сервіс для несанкціонованого доступу до чужих даних або для порушення роботи сайту.',
          ],
        },
        {
          title: 'Каталог, оцінки та зовнішні джерела',
          paragraphs: [
            'Каталожні описи, фото, ціни та курси валют можуть надходити від НБУ, UA-Coins та інших джерел і можуть містити помилки або застарівати. Вони надаються для довідки, не є оцінкою конкретного предмета, гарантією ринкової ціни чи фінансовою порадою. Перевіряйте дані перед купівлею, продажем або іншими рішеннями.',
            'Права на сторонні матеріали належать їхнім правовласникам. Зовнішні посилання, Google, Telegram і monobank працюють за власними умовами; ми не керуємо їхніми сервісами. Пожертви через monobank є добровільними і обробляються на його сайті. Пожертва не є оплатою за доступ до функцій сервісу та не надає додаткових прав або переваг.',
          ],
        },
        {
          title: 'Доступність і зміни',
          paragraphs: [
            'Ми можемо змінювати функції, виправляти помилки, тимчасово обмежувати доступ для технічних робіт або припиняти доступ у разі порушення цих умов. Ми намагатимемося повідомляти про істотні зміни умов на сайті. Актуальна редакція діє з дати, зазначеної вище.',
          ],
        },
        {
          title: 'Відповідальність і звернення',
          paragraphs: [
            'Сервіс надається в доступному стані. Ми докладаємо розумних зусиль для його роботи й захисту даних, але не гарантуємо безперервну доступність або безпомилковість каталожної інформації. Ці умови не обмежують прав споживача, які неможливо обмежити за законом.',
            'Із запитаннями щодо сервісу чи цих умов звертайтеся через кнопку «Підтримка» внизу сайту. До цих умов застосовується законодавство України, з урахуванням обов’язкових прав, які можуть діяти за місцем вашого проживання.',
          ],
        },
      ],
    },
  },
  en: {
    privacy: {
      title: 'Privacy Policy',
      updated: 'Updated: 16 September 2026',
      intro:
        'Bakost Numismatics helps you browse a numismatic catalogue and manage a personal collection and expenses. This policy explains the data processed when you use the site.',
      navigation: 'Document navigation',
      back: 'Back to the site',
      other: 'Terms of Service',
      sections: [
        {
          title: 'Who handles data and how to contact us',
          paragraphs: [
            'The Bakost Numismatics team operates the Bakost Numismatics service. For questions or requests about your data, use the Support button at the bottom of the site. It opens our Telegram bot. Include the email address linked to your account so we can find it. Do not send passwords, sign-in codes or other secrets.',
          ],
        },
        {
          title: 'Data we receive',
          paragraphs: [
            'For your account, we store your email, optional display name and profile photo, email verification status, a password hash (if you set a password), and interface preferences. We also process session information, IP address, browser information and temporary data for email verification or password recovery to provide and protect sign-in.',
            'You enter your own collection and expense information: coins, quantities, condition, storage locations, sellers, purchase dates and places, prices, currencies, notes and images. Some of this may be private or personally important to you; enter only what you want stored in the service.',
            'When you contact support through Telegram, we receive your Telegram ID, username and name where available, plus your messages and attachments. Opening support from the site may link the conversation to your account. Our support team receives these messages in Telegram.',
          ],
        },
        {
          title: 'Google Sign-In',
          paragraphs: [
            'Google Sign-In is optional. If you choose it or link Google to your account, we request basic profile information: your Google account identifier, email address, email verification status and name if available. We store the identifier and email at the time of linking for future sign-in; your name may be used as your profile name. We do not receive your Google password or request access to Gmail or Google Drive.',
          ],
        },
        {
          title: 'Cookies and browser storage',
          paragraphs: [
            'We use necessary cookies to sign you in and maintain your session. Google Sign-In also uses temporary data to complete authentication safely. The relevant sign-in methods cannot work without them.',
            'Browser storage remembers your language, theme, list views and “Remember me” choice. We do not use advertising trackers or third-party analytics trackers.',
          ],
        },
        {
          title: 'Purposes and sharing',
          paragraphs: [
            'We use this data to create accounts, provide sign-in, store your collection and expenses, apply settings, respond to support requests and prevent abuse. Account and collection data is stored in the service’s protected server infrastructure. Access to your records and uploaded images is restricted; someone else may open an image link provided to you by the service if you share that link.',
            'Google processes information needed for the Google Sign-In you choose. We use Resend to deliver email verification and password-recovery messages. Resend receives the recipient’s email address and the data needed to deliver the message. Telegram processes your support messages and attachments under its own rules.',
            'If translation through Anthropic is enabled, a new storage-location name you enter may be sent to Anthropic for translation. Administrative tools may also send catalogue coin titles. This does not mean we send your whole account or collection. Avoid putting personal details in a storage-location name if you do not want them sent for translation.',
            'Catalogue and exchange-rate information may be updated from outside sources without sending them your collection. If you open a source site or the monobank donation page, that site processes visit data under its own rules. Some catalogue images may load directly from an outside source.',
          ],
        },
        {
          title: 'Retention, security and your rights',
          paragraphs: [
            'Account and collection data are kept for as long as the account exists or the data is needed to provide the service or meet legal requirements. After primary data is removed, technical records or backups, if any, may remain for a limited period. The period depends on the data’s purpose and legal requirements; there is no single retention period for everything.',
            'We use encrypted HTTPS connections, access controls, protected password storage and controls for access to personal content. No internet service can guarantee absolute security.',
            'You may ask for access to your data, correction, a copy or deletion, and information about how it is processed. There is currently no automatic account deletion or full-data export in the interface. Contact Support and we will handle your request under applicable Ukrainian law. You may also complain to the Ukrainian Parliament Commissioner for Human Rights or a court.',
          ],
        },
        {
          title: 'Changes',
          paragraphs: [
            'We may update this policy as the service changes. The current version and its update date are always shown here.',
          ],
        },
      ],
    },
    terms: {
      title: 'Terms of Service',
      updated: 'Updated: 16 September 2026',
      intro:
        'These terms govern your use of Bakost Numismatics. By creating an account or using the service, you agree to them.',
      navigation: 'Document navigation',
      back: 'Back to the site',
      other: 'Privacy Policy',
      sections: [
        {
          title: 'Service and account',
          paragraphs: [
            'Bakost Numismatics provides tools to browse a numismatic catalogue and manage a personal collection, expenses and related settings. Personal features require an account. You are responsible for the accuracy of information you provide, protecting your credentials and activity under your account.',
            'Google sign-in is an optional authentication method. Linking Google allows us to use the received information for sign-in as described in the Privacy Policy.',
            'You may stop using the service and contact support to request deletion of your account. The processing and retention of data after such a request are governed by the Privacy Policy.',
          ],
        },
        {
          title: 'Your content',
          paragraphs: [
            'You retain your rights to materials that belong to you. By uploading materials to the service, you confirm that you have the right to use them and grant us the permission necessary to store, process and display them solely to operate the service’s features. Do not post unlawful or harmful content.',
            'We may remove materials or restrict access to them if they violate these Terms, applicable law or the rights of others.',
            'Personal records are intended for your account. Do not attempt unauthorized access to others’ data or disrupt the site.',
          ],
        },
        {
          title: 'Catalogue, prices and outside sources',
          paragraphs: [
            'Catalogue descriptions, photos, prices and exchange rates may come from the National Bank of Ukraine, UA-Coins and other sources; they may be inaccurate or out of date. They are reference information, not an appraisal of a particular item, a guaranteed market price or financial advice. Check information before buying, selling or making other decisions.',
            'Third-party materials belong to their respective owners. External links, Google, Telegram and monobank have their own terms; we do not control those services. Donations through monobank are voluntary and processed on its site. A donation is not payment for access to service features and does not provide additional rights or benefits.',
          ],
        },
        {
          title: 'Availability and changes',
          paragraphs: [
            'We may change features, fix errors, temporarily restrict access for maintenance or suspend access for breaches of these terms. We will try to announce material terms changes on the site. The current version applies from the date above.',
          ],
        },
        {
          title: 'Responsibility and contact',
          paragraphs: [
            'The service is provided as available. We make reasonable efforts to operate it and protect data, but do not guarantee uninterrupted access or error-free catalogue information. Nothing here limits consumer rights that cannot legally be limited.',
            'For questions about the service or these terms, use the Support button at the bottom of the site. Ukrainian law governs these terms, subject to mandatory rights that may apply where you live.',
          ],
        },
      ],
    },
  },
};
